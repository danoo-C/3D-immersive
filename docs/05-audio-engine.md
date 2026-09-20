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

Each minimum-phase HRIR is zero-padded to `nfft = next_pow2(block + N - 1)` and
forward-transformed once. The whole bank lives in memory as
`[M, 2, nfft//2 + 1]` complex64, and is cached to disk keyed by SOFA hash and
block size, so project load does not pay for it twice.

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

    # 3. convolution ----------------------------------------------------
    X = rfft(src, n=self.nfft, axis=1)  # batched, [n, bins]
    H = (self.bank.H[idx] * w[:, :, None, None]).sum(1)  # [n, 2, bins]
    H = H * itd_phase(itd, self.freqs)  # fractional delay

    Y = (X[:, None, :] * H).sum(axis=0)  # SUM OVER SOURCES
    y = irfft(Y, n=self.nfft, axis=1)  # only 2 iFFTs, ever

    # 4. overlap-save, master -------------------------------------------
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
  constant — two transforms whether you have 4 channels or 64. This is the
  single reason a Python engine meets N-1 comfortably.
- **The forward FFT is batched**, one call over a 2D array, not a loop of `n`
  calls. numpy's overhead per call dominates at these sizes; batching is worth
  roughly an order of magnitude.
- **ITD is applied as a phase ramp** in the frequency domain, which gives
  sub-sample delay resolution for free. Sample-quantised ITD produces an audible
  stair-step as a source pans.

### Cost estimate

At 512 frames, `nfft` = 1024, 32 sources: one batched 32×1024 rFFT, a
[32, 3, 2, 513] gather-and-weight, one complex multiply-accumulate, two 1024
iFFTs. That is a few hundred microseconds against a 10.7 ms budget. The margin
is large, which is the point — Python's variance needs headroom, not a tight fit.

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

## Parameter smoothing

Positions change at block boundaries, which would click. Two defences:

- Gains (channel, distance, pan, master) are smoothed per sample with a
  one-pole ramp across the block.
- HRTF changes are handled by the overlap-save tail itself: because the previous
  block's tail was produced with the previous filter and is summed into this
  block, the transition is already a short crossfade. For large jumps — a source
  teleported across the head — we detect an angular delta over a threshold and
  do an explicit two-filter crossfade over the block.

## Scheduler

Given a block `[t, t+block)`, for each channel find the clips overlapping it.
Clips are kept sorted and non-overlapping (see
[03-data-model.md](03-data-model.md)), so this is a cursor advance, not a search.
Clip reads are `numpy` slices out of the resident decoded array at
`offset + (t - start)`, with fade envelopes multiplied in from precomputed
tables.

Seeking resets cursors and zeroes the overlap-save tails.

## Offline render

`render.py` runs the **same** `Engine.process` in a loop with no device, which
is what keeps preview and export from diverging. Differences, all opt-in:

- Smaller block (64) for finer automation resolution.
- Longer HRIRs if the dataset offers them.
- Optional 2× oversampling of the limiter.
- Per-channel stems by rendering with all but one channel muted, reusing the
  same automation — so stems sum exactly to the master. A bypassed channel's
  stem is simply its dry audio, and the sum still reconciles.

Determinism (F-36) comes from: fixed rate and block, no wall-clock anywhere in
the graph, no threads inside `process`, and float32 ops in a fixed order.

## Realtime safety checklist

Enforced by review and by a test that runs `process()` under
`tracemalloc` asserting zero allocation:

- No allocation, no `append`, no f-strings, no `logging` inside `process()`.
- No locks. UI→audio is the command ring; structural changes are an atomic
  snapshot swap.
- `gc.freeze()` after load; explicit collection on the UI thread only.
- Every numpy op writes into a preallocated buffer via `out=`.
- Xruns counted and surfaced in the status bar.

## If Python is not enough

N-1 is the tripwire. If it fails on target hardware, the port is
`Engine.process` and the bank preparation — a few hundred lines — into a
`pybind11`/`nanobind` extension or a Rust `cffi` module, with the same
signature. `core/` and `ui/` are untouched. Nothing above this file needs to
know it happened.
