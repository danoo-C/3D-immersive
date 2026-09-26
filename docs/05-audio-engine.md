# 05 — Audio Engine

## Fixed parameters

| | |
|---|---|
| Internal rate | 48 000 Hz |
| Internal format | float32 |
| Default block | 512 frames (≈10.7 ms), configurable 256–2048 |
| Output | stereo, binaural |
| Automation resolution | one evaluation per block (≈94 Hz at defaults) |

## The HRTF pipeline

### 1. Load

A SOFA file (`SimpleFreeFieldHRIR`) gives an HRIR set: `M` measurement
positions × 2 ears × `N` taps, plus the source position of each measurement.
Loaded with `sofar`, resampled to 48 kHz with `soxr`, and level-normalised so
switching datasets does not change perceived loudness.

Bundled default: a public full-sphere set (SADIE II or ARI) with dense
elevation coverage — required, since we support height.

### 2. Split ITD from spectrum — the step that makes or breaks this

Raw HRIRs must **not** be crossfaded or interpolated directly. Two measurements
a few degrees apart have different inter-aural time delays, and blending them
sums two near-identical signals at slightly different offsets — textbook comb
filtering. The result is a moving source that sounds like it is being flanged.

So each HRIR is decomposed once, at load:

- **ITD** — the broadband inter-aural delay, estimated per direction by
  cross-correlation of the two ears (onset-threshold as a cross-check).
- **Minimum-phase HRIR** — the remaining spectral cue, obtained via the real
  cepstrum, with the delay removed.

Minimum-phase magnitudes interpolate cleanly. Delays interpolate cleanly.
Their sum does not. Keeping them apart is what makes smooth motion possible.

### 3. Spherical interpolation

Measurement directions are unit vectors on a sphere. `scipy.spatial.ConvexHull`
over them yields a triangulation; for a query direction we find the containing
triangle and take **barycentric weights** over its three vertices.

- Minimum-phase HRIRs: weighted sum in the frequency domain.
- ITD: weighted sum of the three scalar delays.

Triangle lookup is accelerated by a `cKDTree` over face centroids — nearest few
candidates, then an exact barycentric test.

### 4. Prepare the bank

Each minimum-phase HRIR is zero-padded to `nfft` and forward-transformed once.
The whole bank lives in memory as `[M, 2, nfft//2 + 1]` complex64, and is
cached to disk keyed by SOFA hash and block size, so project load does not pay
for it twice.

#### Buffer length must account for the ITD

The ITD is applied as a frequency-domain phase ramp (see the per-block
pseudocode), and a phase ramp is a **circular** delay. Anything pushed past the
end of the buffer wraps around to the beginning, which is not a subtle
artefact — it is the tail of the response arriving before the onset.

```
nfft = next_pow2(block + N + max_itd_samples - 1)
```

`max_itd_samples` is the largest ITD in the loaded dataset *after* resampling
— roughly 1 ms, about 48 samples at 48 kHz. It is **computed from the data
at load time, never hardcoded**: a dataset measured on a larger head, or one
resampled from a different rate, will not match the estimate.

#### Delays must be non-negative on both ears

An ITD is a *difference*, so it is natural to write it as +τ on one ear and −τ
on the other. Do not. A negative phase ramp is an advance, and it wraps the
start of the response around to the end of the buffer — the same failure as
above, at the other edge.

Apply the full `|ITD|` as a delay on the **far** ear and `0` on the near ear.
The interaural difference is identical, both ramps are non-negative, and
nothing wraps. The only cost is a constant common delay of up to ~1 ms on the
whole binaural path, which is inaudible and already noted in the bypass
time-alignment caveat below.

## Per-block processing

```python
def process(self, out_l, out_r):  # no allocation below this line
    self._drain_commands()  # lock-free ring from the UI thread
    t = self.playhead

    # 1a. spatialised sources -------------------------------------------
    src = self.src_buf  # [n_active, block], preallocated
    self.scheduler.fill(src, t)  # clip reads, crop, fades, clip gain
    src *= self.channel_gains[:, None]  # channel gain, mute/solo folded in

    # 1b. bypassed channels -----------------------------------------------
    byp = self.byp_buf  # [n_bypassed, 2, block]
    self.scheduler.fill_stereo(byp, t)  # stereo kept, no downmix
    byp *= self.byp_gains[:, :, None]  # channel gain x pan law

    # 2. spatial parameters --------------------------------------------
    pos = self.automation.eval(t)  # [n_active, 3]
    az, el, r = cartesian_to_sofa(pos)
    src *= distance_gain(r)[:, None]  # (ref/r)**rolloff, r clamped

    w, idx = self.bank.weights(az, el)  # barycentric, [n, 3] each
    itd = (self.bank.itd[idx] * w).sum(1)

    H_cur = (self.bank.H[idx] * w[:, :, None, None]).sum(1)  # [n, 2, bins]
    H_cur = H_cur * itd_phase(itd, self.freqs)  # non-negative ramp, far ear

    # 3. convolution, with the filter crossfade ---------------------------
    # The input is windowed, not the output: each source contributes two
    # copies, one fading out against last block's filter and one fading in
    # against this block's. Both are full-length convolutions, so their
    # tails add correctly and nothing is discontinuous anywhere.
    xf = self.xfade_buf  # [2n, block], preallocated
    xf[0::2] = src * self.w_out  # w_out = 1 - w_in
    xf[1::2] = src * self.w_in  # w_in  = linspace(0, 1, block)

    X = rfft(xf, n=self.nfft, axis=1)  # batched, [2n, bins]
    Y = (X[0::2, None, :] * self.H_prev).sum(axis=0) + (
        X[1::2, None, :] * H_cur
    ).sum(axis=0)  # SUM OVER SOURCES, both halves
    y = irfft(Y, n=self.nfft, axis=1)  # 4 iFFTs worth of work, ever

    self.H_prev[:] = H_cur  # carry this block's filter forward

    # 4. overlap-add, master ----------------------------------------------
    y[:, : self.block] += self.tail
    self.tail[:] = y[:, self.block : self.block + self.tail_len]
    y[:, : self.block] += byp.sum(axis=0)  # bypass joins after convolution
    self.master.apply(y)  # gain + limiter
    out_l[:] = y[0, : self.block]
    out_r[:] = y[1, : self.block]
```

Three things worth calling out:

`distance_gain` implements `(ref_distance / max(r, min_distance)) ** rolloff`
from the project's `distance` settings (D-21). The exponent is exposed because
strict `1/r` makes sources vanish faster than most people want when dragging
them outward; it is tuned by ear, not derived.

- **`.sum(axis=0)` before the inverse transform.** Convolution is linear, so
  sources can be summed in the frequency domain. The inverse FFT cost is then
  constant — the same four transforms whether you have 4 channels or 64. This
  is the single reason a Python engine meets N-1 comfortably.
- **The forward FFT is batched**, one call over a 2D array, not a loop of `2n`
  calls. numpy's overhead per call dominates at these sizes; batching is worth
  roughly an order of magnitude.
- **ITD is applied as a phase ramp** in the frequency domain, which gives
  sub-sample delay resolution for free. Sample-quantised ITD produces an audible
  stair-step as a source pans. The ramp is non-negative on both ears and `nfft`
  is sized for it — see *Prepare the bank*.
- **The crossfade is unconditional**, every block, for every source. Why is in
  *Parameter smoothing* below; it is not an optimisation to skip when a source
  is "barely moving".

### Cost estimate

At 512 frames, `nfft` = 1024, 32 sources: one batched 64×1024 rFFT (two
windowed copies per source), a [32, 3, 2, 513] gather-and-weight, two complex
multiply-accumulates, and two 1024-point inverse transforms over a 2-row array
— four iFFTs of work. That is well under a millisecond against a 10.7 ms
budget.

The crossfade roughly doubles the FFT work versus a naive uncrossfaded design.
It is still constant in source count, and the margin is still large — which is
the point. Python's variance needs headroom, not a tight fit.

## HRTF bypass

A channel with `hrtf_bypass` set skips the entire spatial path. Its samples are
read, given clip fades and channel gain, passed through the pan law, and summed
straight into the stereo bus — after the inverse FFT, not through it (step 1b
above).

What bypass switches off, and what it leaves alone:

| Still applied | Skipped |
|---|---|
| Clip gain and fades | HRTF convolution |
| Channel gain, mute, solo | ITD |
| Pan / balance | Distance attenuation |
| Master gain and limiter | Everything positional |

Stereo handling inverts: a spatialised stereo source is downmixed to a mono
point (D-16), because a stereo file has no single position. A **bypassed**
stereo source keeps left and right intact — preserving that image is the whole
reason the switch exists.

### Pan law

Mono source, `p` in [-1, +1]:

```
theta = (p + 1) * pi / 4
L, R  = cos(theta), sin(theta)      # constant power, -3 dB at centre
```

Stereo source: balance rather than pan. `p > 0` attenuates the left channel by
`1 - p` and leaves the right untouched, and vice versa, so a centred setting is
bit-transparent. Folding a stereo image with a pan law instead would quietly
damage exactly the material bypass was meant to protect.

### It is cheaper, not just different

Bypassed channels never enter the FFT. A project whose heaviest element is a
long bypassed backing track costs almost nothing extra to play, since that
track contributes a buffer copy and a multiply rather than a convolution. This
is worth knowing when reading the M4 benchmark: N-1's 32 sources means 32
*spatialised* sources.

### ⚠️ Time alignment caveat

The two paths are not sample-aligned. A binaural source carries the HRIR's
propagation delay plus its ITD — together roughly 0 to 1 ms depending on
direction — while a bypassed channel has none.

This does not matter for unrelated material, which is the normal case. It
matters if the same sound is split across both paths — the common trick of
spatialising the top end of a source while keeping its sub bypassed. There the
two will interact in phase, and moving the spatialised copy will make the low
end shift in level.

Not solved in v1. Documented because it will otherwise be reported as a bug in
the bypass feature when it is really a property of splitting a source across
two paths. If it proves annoying, the fix is a per-channel delay in samples,
which is a small addition — not a redesign.

## The master bus

Everything — convolved sources after the inverse FFT, bypassed channels summed
in beside them — lands on one stereo bus, which applies master gain and then
the limiter.

### The limiter

One fixed design, not a configurable one (D-54). `master.limiter_on` stays a
boolean, and there are no controls to set:

| | |
|---|---|
| Type | brickwall peak limiter |
| Ceiling | −0.3 dBFS |
| Lookahead | 1.5 ms (72 samples at 48 kHz), **internally compensated** |
| Attack | the lookahead |
| Release | 50 ms, smoothed |
| Knee | 2 dB soft |

This is not a mastering tool, and a limiter with six controls is six more
things to get wrong in a mix whose point is somewhere else entirely. The
ceiling sits below 0 dBFS because an inter-sample peak in a 24-bit file that
measures exactly 0 will still clip somebody's converter.

⚠️ **The lookahead is compensated inside the limiter**, and that is
load-bearing rather than tidy. Lookahead is what separates a limiter from a
clipper — it needs to see the peak before deciding — but it delays whatever
passes through it. Stems skip the limiter (D-41), so an *uncompensated*
lookahead would leave the master 72 samples later than the stems that are
supposed to sum to it, and M7's exactness test would fail against a constant
offset nobody had written down. Compensating it also keeps preview and render
time-aligned, which is the property the whole offline-reuses-`process` design
exists for.

Nothing in it is stochastic, so F-36's determinism survives it. It is the only
nonlinear block in the graph, which makes it the one place where "deterministic
per machine and build" (D-40) is worth re-checking after a numpy upgrade.

### Metering

The bus also publishes a peak per side for the master meter (F-54): the
highest level each side has reached since the UI last took them. The audio
thread raises two floats in a preallocated array; the UI reads both and sets
them back to zero at frame rate (`Engine.take_peaks`). No history, no
allocation, no lock: a block that lands between the read and the reset is one
frame of a meter, which nobody can see. The hold and decay a meter shows are
the meter's own, drawn on the UI thread.

Per-channel meters are deliberately absent (D-55). What the master meter is
*for* is the thing that is genuinely hard to predict here: 32 sources summing
in the frequency domain, each already scaled by a distance attenuation that
moves while it plays. A fader position does not tell you what reaches the bus.

## Parameter smoothing

Positions are evaluated once per block, so without care every parameter in the
graph steps discontinuously ~94 times a second. Two separate mechanisms.

### Gains: a per-sample ramp

Channel, distance, pan and master gains are smoothed per sample with a linear
ramp across one block: each sample moves an equal step from where the last
block left the gain, and the block's last sample lands on the new value. Cheap,
and scalar gains have no memory, so nothing more is needed. Linear rather than
the one-pole this section first named, because a one-pole never arrives: a
gain that has reached its target costs one multiply per sample, or none at
0 dB, which is what keeps a whole-sample clip bit-transparent (D-42). Mute and
solo are gains of nothing (D-105), so they ramp too, and do not click.

### Filters: an unconditional per-block crossfade

⚠️ **The overlap-add tail does not smooth a filter change.** It is tempting to
think it does — the previous block's tail was produced with the previous filter
and is summed into this one — but the tail only carries the *decay* of the
response. The direct sound of block *k* is convolved entirely with `H_k`, so at
every block boundary the direct path switches filters instantly. HRIRs put
nearly all of their energy in the first millisecond, so that is an abrupt
switch, 94 times per second.

It is not a corner case. A source orbiting once per second moves about 4° per
block, which is roughly a one-sample ITD step per block on the far ear. On
transient material you may not notice; on sustained material — pads, strings, a
held tone — it is an audible buzz at the block rate. A threshold on
"large angular jumps" does not catch it, because no individual step is large.

⚠️ **How audible depends on how fast the source moves, and S0 measured it.**
"Clearly audible" was this paragraph's original wording and it is too strong at
the bottom of the range. Block-rate sidebands on an orbiting 440 Hz sawtooth,
crossfaded versus not:

| orbit | ° per block | crossfaded | none | what the crossfade buys |
|---|---|---|---|---|
| 1 rev/s | 3.8 | −69.6 dB | −35.9 dB | 33.7 dB |
| 2 rev/s | 7.7 | −62.1 dB | −31.3 dB | 30.8 dB |
| 4 rev/s | 15.4 | −46.6 dB | −29.0 dB | 17.5 dB |
| 8 rev/s | 30.7 | −39.0 dB | −30.4 dB | 8.6 dB |

At 1 rev/s the uncrossfaded artefact sits at −35.9 dB and a listener described
that render as realistic, with no buzz — it took an A/B to hear a difference at
all. At 4 rev/s the same listener called the uncrossfaded file *"horrible, like
a dial-up tone under the sound"*, unprompted. So the buzz is real and the
crossfade is necessary; it simply does not announce itself until the source
moves at a fair pace.

Two consequences, both recorded as D-70. The crossfade's *benefit* shrinks as
the source speeds up — the uncrossfaded artefact barely moves while the
crossfaded render degrades, because a linear blend approximates a smooth
trajectory badly once the step is large — so very fast motion keeps some
artefact whatever the crossfade does, and the fix if it ever matters is
sub-block filter updates rather than a longer fade. And the *unconditional*
rule below is vindicated rather than softened: the quiet end of the range is
precisely where a "large jump" threshold would decline to fire.

So the crossfade is **unconditional: every block, every source** (D-37).

Crossfade by windowing the **input**, not the output:

```
y = (x_k · w_out) * H_prev  +  (x_k · w_in) * H_cur

w_in  = linspace(0, 1, block)
w_out = 1 - w_in
```

Windowing the input rather than the output is what makes this correct rather
than merely better. Both halves are full-length convolutions, so each carries
its own correctly-tapered tail into the next block, and the sum is continuous
everywhere — including in the tail, which an output crossfade would chop.

Bookkeeping:

- `H_prev` — the per-source filter weights *and* ITD from the previous block —
  is stored alongside the engine state and updated at the end of each block.
- On seek, and after an atomic snapshot swap, set `H_prev = H_cur` so the first
  block after the discontinuity does not crossfade from a stale filter.
- There is no large-jump special case. A teleported source is handled by the
  same code path as a slowly drifting one; it simply crossfades over one block.

## Scheduler

Given a block `[t, t+block)`, for each channel find the clips overlapping it.
Clips are kept sorted and non-overlapping (see
[03-data-model.md](03-data-model.md)), so their ends are sorted too, and the
first clip a block needs is one binary search on them. This section first
named a cursor advanced along the clips; at tens of clips a channel the search
costs as little, and it keeps no state, so a seek or a snapshot swap has no
cursor to reset. Clip reads are `numpy` slices out of the resident decoded
array at `offset + (t - start)`, with fade envelopes multiplied in from
precomputed tables.

**What plays is a snapshot** (D-105): each channel's clips with their samples,
their gain as a factor, and their head and tail tables, built on the UI thread
and never written after. A channel's gain, mute and solo arrive separately,
through the command ring, as one linear gain each.

**A fade is sampled from `FadeShape.gain`**, the curve the clip draws. A
fade-in `L` samples long is `gain(k / L)` at its `k`th sample, so its first
sample is silent and the one after it whole; a fade-out is the same table
backwards, so its last sample is silent. Tables are shared between clips with
the same fade, and read-only.

### Implicit edge fades

A clip edge with `fade.length = 0` starts or stops the waveform at whatever
value it happens to hold, which clicks — and after a split or a trim, edges
land mid-waveform by definition.

So the scheduler applies an **implicit 32-sample linear fade** at any clip edge
that is not at the media file's own boundary — that is, unless `offset == 0`
for the head, or `offset + length == MediaFile.frames` for the tail. A
full-length stem placed at 0 therefore stays bit-transparent, which matters
because that is exactly the bypassed-backing-track case (D-32).

The implicit fade is not stored in the project and not drawn in the UI. An
explicit fade replaces it rather than adding to it, and it is never more than
half the clip. See the Rules in [03-data-model.md](03-data-model.md).

Seeking moves the playhead, through the command ring so it cannot race a swap.
From M4 it also zeroes the overlap-add tails and sets `H_prev = H_cur`; the
flat engine has neither.

## The output stream

The stream is always opened at **48 kHz** (D-11, D-63). There is no output
resampler: putting a second rate converter inside the callback to paper over a
device mismatch costs latency and quality to hide something that is better
reported.

If a backend refuses 48 kHz, that is a reported failure (F-56), not a silent
fallback, and the device list marks which devices will accept it. In practice
the shared-mode backends — WASAPI, CoreAudio, PipeWire — accept 48 kHz and
convert behind their own mixer, so this bites mainly on exclusive-mode and
fixed-rate hardware, which is exactly where the user wants to know.

Device and block size are selectable (F-55). The preferences UI for them is
M8, and the first audio is M2, so in between they are command-line flags —
`--device` and `--block` — rather than five milestones in which a wrong
default device makes the application look broken with no way out.

A device that disappears mid-session (headphones unplugged, an interface
powered off) stops the stream. The playhead holds position, the failure is
reported, and reopening is a user action — silently migrating a mix to the
laptop speakers mid-audition is a worse outcome than stopping.

## Offline render

`render.py` runs the **same** `Engine.process` in a loop with no device, which
is what keeps preview and export from diverging. Differences, all opt-in:

- Smaller block (64) for finer automation resolution.
- Longer HRIRs if the dataset offers them.
- Optional 2× oversampling of the limiter.
- Per-channel stems by rendering with all but one channel muted, reusing the
  same automation. A bypassed channel's stem is simply its dry audio.

### Stems are rendered pre-limiter

Stems sum to the **pre-limiter** master, not to the delivered master file
(D-41). The limiter is nonlinear: it responds to the summed signal, so the
gain reduction applied to a full mix cannot be decomposed into per-stem
contributions. Rendering stems through it and claiming they sum would be
false whenever it engages — which is to say, whenever it matters.

Stems are therefore unlimited. The master render applies the limiter; the stem
render skips it. The exactness property is preserved against a pre-limiter
master, and that is what the M7 test asserts.

### Dither

The bus is float32 and the file is 24-bit fixed, so the conversion truncates
unless something is done about it. **TPDF dither at 1 LSB, from a generator
seeded with a constant** (D-56).

At 24 bits the difference is inaudible either way, so dither is not really the
question — determinism is. Truncation correlates the error with the signal,
which is the textbook reason to dither at all; dithering from an unseeded
generator would make two renders of the same project differ in the last bit
and turn F-36 into a test that fails mysteriously. Seeding it makes the noise
part of the deterministic output, which is the only version of "dithered and
bit-identical" that is true.

Stems are dithered on the same terms, from the same seed.

### Determinism

Determinism (F-36) comes from: fixed rate and block, no wall-clock anywhere in
the graph, no threads inside `process`, a seeded dither generator, and float32
ops in a fixed order. That guarantees bit-identical output **across runs on one
machine and build** — not across platforms, where FFT library versions and SIMD
dispatch legitimately differ in the last bits.

## Realtime safety checklist

Enforced by review and by a test that runs `process()` under
`tracemalloc` asserting zero allocation. In Python that means what D-106 says:
no memory kept from one block to the next, and no numpy array made inside a
block. A slice is a view and an integer past 256 is an object, and those few
dozen bytes are not what the rule is for. The test runs 500 blocks of 2048
frames through every path, and fails on anything kept or on any block raising
traced memory's peak by 2 KiB:

- No allocation, no `append`, no f-strings, no `logging` inside `process()`.
- No locks. UI→audio is the command ring; structural changes are an atomic
  snapshot swap.
- `gc.freeze()` after load; explicit collection on the UI thread only.
- Every numpy op writes into a preallocated buffer via `out=`.
- **No ufunc broadcasts.** A `(B, 1)` ramp over a `(B, 2)` block allocates
  17 KiB behind `out=`, measured. Buffers are planar, one contiguous row per
  ear, and a ramp is applied a row at a time.
- **numpy ≥ 2.0 is required, not merely preferred.** The rule above is only
  achievable because `np.fft.rfft` and `np.fft.irfft` accept `out=` and operate
  on float32 without silently upcasting to float64. Both arrived in numpy 2.0.
  On numpy 1.x the FFT calls allocate a fresh float64 array every block, inside
  the callback, which is precisely what this checklist exists to forbid.
- Xruns counted and surfaced in the status bar.

## If Python is not enough

N-1 is the tripwire. If it fails on target hardware, the port is
`Engine.process` and the bank preparation — a few hundred lines — into a
`pybind11`/`nanobind` extension or a Rust `cffi` module, with the same
signature. `core/` and `ui/` are untouched. Nothing above this file needs to
know it happened.
