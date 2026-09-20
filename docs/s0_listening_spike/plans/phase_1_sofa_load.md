# Plan — S0 · Phase 1 — SOFA load

**Written:** 2026-09-20 · **Status:** ✅ complete

## Approach

One script, `spikes/binaural_spike.py`, grown a phase at a time. This phase
adds the front end: fetch a dataset once into a gitignored cache, load it,
validate it, convert the measurement positions to unit vectors, resample to
48 kHz and normalise the level. It ends with `--info` printing everything a
reader needs to believe the set is what it claims to be.

**Dataset: SADIE II D1** (the KEMAR dummy head), from the sofacoustics.org
mirror:

```
https://sofacoustics.org/data/database/sadie/D1_48K_24bit_256tap_FIR_SOFA.sofa
```

36.6 MB, already 48 kHz, 256 taps. Verified reachable while writing this plan.
Two things recommend it over the alternatives: it is a *dummy head*, so nobody
is listening to someone else's ears, and the roadmap names SADIE II first.

Rejected alternatives, both with reasons worth keeping:

- **The York URL in the roadmap's prose** — `www.york.ac.uk/sadie-project/…`
  now 404s. That is why this plan pins the mirror and records a checksum rather
  than a URL alone.
- **ARI** (`ari/hrtf b_nh*.sofa`) — reachable, but its grid stops at −30°
  elevation, which would fail this phase's full-sphere acceptance line outright.
  Kept as the fallback *only* if D1's licence turns out to forbid even local
  use, in which case the coverage acceptance has to be renegotiated explicitly
  rather than quietly relaxed.

**The checks live in the script, not in `tests/`.** Every acceptance line below
is verified by a `--check` mode that the script runs against the loaded set.
Putting them under `tests/` would make CI download 36 MB on every matrix leg
for a throwaway script, and `pytest`'s `testpaths` is deliberately `["tests"]`.
The spike verifies itself; CI never sees it.

## Steps

1. **Fetch and cache.** `spikes/binaural_spike.py` with a `--info` entry point
   and a fetch helper using `urllib.request` — stdlib, since the spike's
   dependency list is numpy/scipy/`sofar`/`soxr` and nothing else. Downloads to
   `spikes/data/`, records the SHA-256 beside it, and re-verifies on every run
   so a truncated download fails loudly now rather than as a strange artefact
   in phase 4. Add `/spikes/data/` to `.gitignore` in this step.
   *Test:* run twice; the second run does no network I/O and still succeeds
   with the interface down.

2. **Load and validate.** `sofar.read_sofa`, then assert
   `GLOBAL_SOFAConventions == "SimpleFreeFieldHRIR"` and print
   `GLOBAL_License`, `GLOBAL_DatabaseName`, `GLOBAL_Title`, `M`, `N`, the
   stored sample rate and the `Data_Delay` field. If `sofar`'s verification
   rejects the file, fall back to `verify=False` and *print* what failed —
   a dataset that is slightly non-conforming is usable; one that is silently
   coerced is not.
   *Test:* `--info` prints a licence string that also appears in the raw file,
   proving it was read rather than hardcoded.

3. **Directions to unit vectors.** Convert `SourcePosition` (spherical degrees)
   to unit vectors. The spike keeps its bank in **SOFA's frame** (+x front,
   +y left, +z up) and converts at the query boundary only, using the
   `cartesian_to_sofa` formula in [03-data-model.md](../../03-data-model.md) —
   one conversion, in one place, so phase 3's hull and phase 4's queries cannot
   disagree about which way is left.
   *Test:* round-trip 1 000 random project-frame directions through
   `cartesian_to_sofa` and back, agreeing within 1e-6; assert the coverage
   bounds (a measurement above +60° and one below −30°) and print the actual
   elevation range.

4. **Resample to 48 kHz.** `soxr.resample` per ear, into a float32
   `[M, 2, N48]` array. For D1 this is a no-op, which is a trap: the path must
   still be exercised.
   *Test:* a synthetic 44.1 kHz impulse response resampled to 48 kHz has the
   expected length and preserves broadband energy within 0.1 dB; and for a set
   already at 48 kHz the output is bit-identical to the input.

5. **Level normalisation.** Divide the whole set by the RMS averaged over all
   directions and both ears, then apply a fixed headroom factor so the loudest
   single direction peaks below 1.0. Print the applied gain in dB, the
   resulting mean RMS and the post-normalisation peak.
   *Test:* mean RMS within 0.5 dB of the target; peak strictly below 1.0; no
   NaN or Inf anywhere in the array.

Five steps, inside the six the workflow allows. If step 3 turns into a fight
about conventions, it is a phase of its own and this one ends at step 2.

## Files

```
spikes/binaural_spike.py    new — this phase writes roughly the first 90 lines
spikes/data/                new — gitignored download cache
.gitignore                  amended — /spikes/data/
```

Nothing under `src/`, nothing under `tests/`.

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| D1's licence forbids redistribution | Nothing here — the spike never redistributes. It matters at M4 bundling | Print it, record it in the phase Notes, hand it to QA-30 |
| D1's elevation coverage does not reach below −30° | The full-sphere acceptance line fails | Step 3 prints the real range before anything depends on it. If it fails, say so and renegotiate the acceptance in the open — a dummy-head set with a hole under the chin may simply be what exists |
| sofacoustics.org goes the way of the York link | The next person cannot reproduce the run | SHA-256 recorded in the script beside the URL, so a mirror can be verified against it |
| `sofar` rejects the file's conventions | Half a day | Step 2's `verify=False` fallback, with the failures printed |
| The 36 MB download on a metered connection | Annoyance | Cached on first run; never fetched by CI |

The genuine unknown is the stored `Data_Delay` field. Some datasets carry a
per-measurement delay there that must be added to the ITD rather than ignored.
It is read and printed in step 2 precisely so phase 2 inherits a fact rather
than an assumption.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| ITD extraction, minimum phase | [phase 2](../phase_2_itd_minimum_phase.md) |
| Triangulation, the KD-tree | [phase 3](../phase_3_interpolation.md) |
| `nfft`, the bank, any FFT at all | [phase 4](../phase_4_block_engine.md) |
| Caching the *prepared* bank to disk | M4 — the spike reloads each run, and at this size that is fine |
| Choosing the bundled default dataset | QA-30, decided at M4. This plan chooses what the spike *runs on*, which is a smaller claim |

## Amended while building

Two departures from the steps above, left visible rather than tidied away.

**Step 4's test was wrong as written.** It asserted that resampling preserves
broadband energy; it does not, and should not. `soxr` preserves the
continuous-time waveform, so an impulse resampled 44.1 → 48 kHz gains +0.15 dB
of discrete energy and its sample sum scales by exactly the rate ratio — which
is the correct behaviour for a filter, because discrete convolution
approximates the continuous one scaled by `1/fs`. The test now asserts the
frequency response, `|H(f)|` scaled by `1/rate`, which is the property the
convolution actually depends on. It holds to 0.06 dB from 100 Hz to 15 kHz.

**The checks moved to `spikes/checks.py`.** Written as one file, the spike hit
280 lines at the end of phase 1 against the roadmap's ~300-line constraint,
with four phases still to come — and roughly a third of that was the check
mode. Test code is not what a script's line budget is measuring, so the checks
became a sibling module: still outside `src/`, still never run by CI, still one
command to invoke. The spike proper ends phase 1 at 227 lines, which leaves
room for the DSP that is the actual point of it.

## Outcome

All seven acceptance lines pass; `python spikes/binaural_spike.py --check`
prints eleven checks and exits zero.

**The dataset was the easy part.** SADIE II D1 loaded first try: 8802
positions, −90° to +90° elevation, 256 taps, already 48 kHz, and **Apache 2.0**
— permissive enough to bundle, which is better than this plan dared assume and
is the strongest evidence QA-30 has so far. Neither fallback was needed. The
plan's worry about elevation coverage was misplaced for a dummy-head set.

**What the plan got right that mattered:** printing `Data_Delay` rather than
assuming it. It is zero here, which closes the question for phase 2 — but the
line of code that would have hidden a non-zero value is the same line either
way, and now the next dataset cannot surprise anyone quietly.

**What it got wrong:** the energy test above, and the line budget. It also
did not anticipate that normalising to unity pair power would clip — the set
peaks at 1.065 at that target — so the "fixed headroom factor" it waved at
had to become a concrete number, 0.25 per ear, asserted.

**Inherited by phase 2:** a `[8802, 2, 256]` float32 array at 48 kHz,
normalised, with unit direction vectors in SOFA's frame beside it and no
stored delay to account for. `max_itd_samples` is phase 2's to measure; with
N = 256 it decides whether phase 4's `nfft` is 1024, and everything so far says
it will be.
