# Plan — M2 · Phase 2 — Decode and resample

**Written:** 2026-09-24 · **Status:** ✅ complete

## Approach

One function, `decode(path)`, in `core/io/media.py`, returning either a
`Decoded` — float32 audio at 48 kHz, shaped `(frames, channels)`, with the
rate it came from — or a `Refused` carrying a reason a person can read. It
never raises on input. That is the split M9 drew for theme files and it
holds here for the same reason: a sample that will not open is a fact about
the sample, and phase 6 has to turn a folder of them into one notice rather
than stop at the first.

The alternative — raise, and let the caller catch — was rejected because
`soundfile` raises one exception type, `LibsndfileError`, for everything from
"not audio" to "not there", and its messages for the two most common cases
are *System error.* and *Format not recognised.* A caller that catches has to
re-derive what went wrong; this module is the only place that can say it
well.

`core/` cannot use `ui/notices.py`'s `Severity` (N-5 forbids `core` importing
`ui`), so a refusal carries a reason and no severity. Phase 6 decides that a
file that could not be imported is a warning, because it is the one that
knows the file was one of forty.

## What was measured before writing this

A probe against the installed `soundfile` 0.14.0 and `soxr` 1.1.0, so the
plan argues from behaviour rather than documentation:

| Question | Answer |
|---|---|
| Which libsndfile? | the wheel's own, 1.2.2, loaded before any system copy |
| MP3? | reads **and writes** — so the tests can generate MP3 fixtures rather than commit binaries |
| `soxr`'s frame count | the exact ratio `n · 48000 / rate`, rounded half up, for every rate and length tried |
| Header-truncated, empty, text named `.wav` | `LibsndfileError` |
| Missing file, a directory | `LibsndfileError` saying *System error.* and *Format not recognised.* |
| Truncated in the middle of the data | **decodes silently shorter**; libsndfile adjusts its frame count to what is there |
| Zero frames | decodes, to nothing |
| Float WAV above 0 dBFS | passes through at 2.0 |
| Six channels | decodes |
| Five minutes of stereo, 44.1 kHz | decode 0.23 s (FLAC), 0.26 s (MP3); resample 0.26 s at `HQ`, 0.38 s at `VHQ` |

## Three things the phase doc leaves open

Rows in the decision log, written in step 1.

### F-5's fallback decoder is not needed

F-5 says "whatever libsndfile + a fallback decoder cover", written when
libsndfile had no MP3. It has since 1.1, and `soundfile` wheels carry their
own on every platform. The evidence for this machine is the table above; the
evidence for the other two is a test asserting MP3 is among the available
formats, which runs on every CI leg. A second decoder would be a dependency
carried for a case no supported install produces.

### More than two channels is refused, not downmixed

`03` says a `MediaFile` has one or two channels. A six-channel file could be
folded down, but "down" means different things: a 5.1 mix has a standard
downmix, a four-channel B-format recording has none that is not nonsense, and
a multitrack export of unrelated stems has no downmix at all. Guessing would
produce a stereo file that sounds plausible and is wrong. Refusing, with the
channel count in the reason, costs a person one export from the tool that
made the file. Multichannel input is out of scope for v1 in
[00](../../00-overview.md) already.

### What "within ±1" means for float sources

The phase doc asks that 16-bit, 24-bit and float sources all come back within
±1. For **integer** sources that is a property of the conversion and is
asserted. For **float** sources it is not true and should not be: a float
file can legitimately hold 2.0, and clipping it on import would change the
audio before anyone heard it. Overs are the master limiter's business (D-54).
So float passes through untouched, and the acceptance line is ticked on that
reading, said here rather than narrowed quietly.

## Steps

1. **The reader and its refusals.** `decode(path) -> Decoded | Refused`:
   missing, a directory, unreadable, not audio, no frames, more than two
   channels — each a reason. Formats from generated fixtures, MP3 included.
   The two decision rows, the high-water mark, F-5's wording pointed at the
   first of them.
   *Test:* each F-5 format decodes; MP3 is an available format; every
   refusal's reason names what was wrong; a battery of hostile inputs raises
   nothing; `Decoded.audio` is float32, `(frames, channels)`, C-contiguous
   and read-only.

2. **Resampling, and the facts a `MediaFile` records.** `soxr` at `HQ` when
   the rate is not 48 kHz, untouched when it is; the frame rule; integer
   formats within ±1 and float passed through; `Decoded.media_file(id, path)`
   filling `name` (the file's name, as `03`'s example has it), `source_rate`,
   `channels` and `frames`. `03` gains the frame rule and the float rule.
   *Test:* 22.05, 44.1 and 96 kHz come back at the rule's frame count
   exactly; a 1 kHz tone's spectral peak is still at 1 kHz within a bin; a
   48 kHz source comes back bit-identical; the integer and float cases above.

## Files

```
docs/01-requirements.md            amended — two decision rows, F-5 pointed
                                     at the first
docs/doc-system.md                 amended — the D high-water mark
docs/03-data-model.md              amended — the frame rule, float, name
docs/m2_media/phase_2_*.md         amended — Notes
src/immersive/core/io/media.py     new
tests/test_media.py                new — headless, fixtures generated
```

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| A platform's wheel without MP3 | MP3 import fails there and nowhere else | the available-formats test runs on all three CI legs, which is exactly where it would show |
| Fixtures written by the same library that reads them | a round trip that proves only that libsndfile agrees with itself — M1 phase 5's lesson | assert what was *written* independently: the tone's frequency by FFT, the frame count by the rule, not by comparing reader to writer |
| `HQ` rather than `VHQ` | 20-bit rather than 28-bit precision in the resampler | 20 bits is −120 dB, below anything a float32 mix can show; `VHQ` costs half as much again at every project load, and N-4 has a budget |
| Memory | five minutes of stereo is 115 MB of float32 | noted for phase 6 and M3; the roadmap says hold it in RAM, and a decoded-audio cache is `03`'s later option |

**Mutations named in advance**, run against the whole suite with
`PYTHONDONTWRITEBYTECODE=1` and a purged `__pycache__`:

| | |
|---|---|
| a 48 kHz source resampled anyway | a no-op pass that still changes samples |
| no source resampled at all | 44.1 kHz material plays eight percent fast |
| `source_rate` recorded as 48000 | the file's own rate lost, and relink cannot compare it |
| float sources clipped to ±1 | a legitimate over flattened on import |
| integer sources returned as float64 | twice the memory, and a dtype the engine's `out=` buffers reject |
| mono returned one-dimensional | every caller has to special-case mono |
| six channels downmixed instead of refused | a plausible, wrong stereo file |
| zero frames accepted | a clip of nothing, with a thumbnail of nothing |
| `LibsndfileError` allowed through | one bad file stops a folder import |
| a missing file reported as *System error.* | the reason libsndfile gives, which says nothing |
| the audio left writable | a clip that edits the sample every other clip shares |
| `name` as the stem | `kick.wav` and `kick.mp3` indistinguishable in the pool |

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The content hash | phase 3 |
| Peaks | phase 4 |
| Decoding on a worker thread | phase 6, which calls this |
| Detecting a file truncated in the middle of its data | not available through libsndfile, which reads what is there and reports that as the length — recorded in the Notes rather than claimed |
| A decoded-audio cache | `03`'s later option, if re-decoding on load proves too slow |

## Outcome

Two steps, committed together because neither meant much alone; all seven
acceptance boxes ticked, one on the reading this plan gave in advance.
Thirteen mutations, one survivor on the first run, and that survivor
disproved a claim this plan made. 895 tests.

### What the plan got right

**Measuring before planning.** Every open question the phase doc left was
answered by a probe before a line of the plan was written, and none of the
answers changed afterwards. The one claim the plan made *without* measuring —
that a no-op resample moves samples — is the one that turned out false.

**Refusing rather than raising.** The hostile-input battery found nothing to
fix, because the design never gave an exception a way out.

### What the plan did not see

**That `soxr` is exact at equal rates.** The mutation table says resampling a
48 kHz file anyway is "a no-op pass that still changes samples"; it changes
nothing. The check survives as a saving of one whole-file copy, now asserted
as such.

**That the evidence for other platforms could be had today.** The plan said
CI would supply it. Downloading the three wheels and reading their bundled
libraries was quicker than waiting, and more direct.

### Deviations

| Planned | Actual |
|---|---|
| Two commits, one per step | one — the reader without the resampler would have returned audio at the wrong rate under a type that promised 48 kHz |
| The platform evidence from CI | from the wheels themselves, with CI's test kept as the standing check |

### What phase 3 needs to know

`Decoded.media_file(id, path)` fills every field except `hash`, which is
phase 3's. `03`'s own example writes a hash as `sha256:…`, which is a lead
rather than a decision. A refusal is a `Refused` with a reason and no
severity; whoever reports it decides how serious it is. And the audio is
read-only, so a hash computed over it can never be invalidated by a clip.
