# Plan — S0 · Phase 3 — Spherical interpolation

**Written:** 2026-09-21 · **Status:** ✅ complete

## Approach

`scipy.spatial.ConvexHull` over the 8802 unit vectors. For points on a sphere
the convex hull *is* the spherical Delaunay triangulation, so this costs one
call and gives the triangulation for free. Verified while writing this plan: it
returns **17 600 faces in 0.07 s**, which is exactly `2N - 4`, the Euler
characteristic of a closed triangulated sphere with no degeneracies. The set
has no duplicate directions and exactly one measurement at each pole, both
checked.

**Containment by matrix solve, not by geometry.** Build `M` from a triangle's
three unit vectors as columns; then for a query direction `q`, solving
`M @ [a, b, c] = q` gives coefficients whose normalised form
`[a, b, c] / (a + b + c)` is exactly the barycentric coordinate of where the
ray from the origin pierces the triangle's plane. The direction lies in the
spherical triangle if and only if all three are non-negative. So one 3×3
inverse per face, precomputed once for all 17 600, turns both the containment
test and the weights into a single `einsum` — no ray-plane intersection, no
spherical trigonometry, nothing to get wrong at a pole.

**Candidate selection is tiered, with an exact fallback.** A `cKDTree` over
face centroids, querying `k = 32` and then `k = 128`, and if both miss, a
containment test against every face. Measured over 10 000 seeded directions:

| candidate set | resolves | cost |
|---|---|---|
| `k = 8` | 83.8% | 2.5 µs |
| `k = 32` | 98.95% | 7.1 µs |
| `k = 128` | 100% | 29.7 µs |

The tiers are the optimisation; **the fallback is the correctness argument.**
`k = 128` resolving 100% of ten thousand directions from one seed is not the
same claim as "every query finds a containing triangle", which is what the
acceptance asks for. A closed hull guarantees a containing face exists, so an
exhaustive test cannot fail — and with the cheap tiers in front of it, it
almost never runs.

**Rejected: indexing faces by their vertices.** The obvious alternative —
nearest measurement vertex, then test the faces touching it — is pathological
on this grid. Each pole is a single measurement fanning out to an entire ring,
so **one vertex touches 400 faces**, and a padded vertex→faces table costs 400
slots for all 8802 vertices. Measured at 40 µs for one nearest vertex (and
still only 99.92% — the containing triangle need not touch the nearest vertex)
and 112 µs for two. Worse on both axes than the centroid tree.

## Steps

1. **Hull, inverses, tree.** `ConvexHull` over `directions`; `[F, 3, 3]`
   inverses via `np.linalg.inv`; centroids normalised back onto the sphere;
   `cKDTree` over them.
   *Test:* `F == 2 * M - 4`, so the hull is closed and no measurement was
   dropped as interior; every face matrix inverts with a condition number below
   a sane bound, which is what a degenerate (collinear) triangle would fail.

2. **The tiered query.** Returns `(face, weights)` for a batch of directions:
   `k = 32`, then `k = 128` on whatever is left, then the exhaustive test on
   whatever is still left. Structured so the fallback is reached by the same
   code path, not a special case.
   *Test:* 10 000 pseudo-random directions, fixed seed — every one resolves,
   weights sum to 1.0 within 1e-6, no weight below −1e-9. Print how many
   directions each tier resolved, because that is the number that says whether
   the tiers are still earning their place on the next dataset.

3. **Querying exactly at a measurement.** The degenerate case worth its own
   step: the query sits on a vertex shared by several faces, and any of them is
   a correct answer provided the weight on that vertex is 1.
   *Test:* six measured directions including both poles return a top weight
   above 0.999. Measured while planning: 1.000000.

4. **Interpolating the ITD, and the two continuity sweeps.** The weighted sum
   of the three vertices' signed ITDs. Signed, not magnitude-plus-far-ear —
   interpolating a magnitude across the median plane would fold two opposite
   delays into a false zero. Convert back to the phase 2 representation after
   interpolating.
   *Test:* a 1°-stepped horizontal orbit and an elevation sweep from −40°
   through overhead and down the far side; the interpolated ITD changes by less
   than one sample between adjacent steps, printed as a max-step figure. Also
   assert the max step **at a triangle boundary** is no worse than the max step
   within one, which is what "no jump at a triangle boundary" actually means.

5. **Timing.** Median scalar lookup, and the batched per-source figure.
   *Test:* median under 50 µs.

Five steps, inside the six [09-workflow.md](../../09-workflow.md) allows.

## Files

```
spikes/binaural_spike.py    amended — hull, inverses, tree, the tiered query,
                            ITD interpolation, --info additions
spikes/checks.py            amended — the phase 3 check block
```

Nothing under `src/`, nothing under `tests/`.

## Risks and unknowns

| Risk | What it costs | Mitigation |
|---|---|---|
| **The horizontal continuity bar has almost no margin.** Measured max step is **0.914 samples** against a limit of 1.0 | The acceptance line fails on a dataset one notch coarser, and it will look like a bug in this phase | It is measured and printed, not asserted blind. Note also that 0.914 is roughly twice the smooth sine-law slope at that azimuth, so about half of it is roughness in the measured field rather than anything interpolation did. If it ever fails, the question is the grid, not the code |
| The tiers are tuned against one dataset and one seed | Nothing, by construction | The exhaustive fallback is the guarantee; the tiers only decide how often it runs. The per-tier counts are printed so a set that stops fitting them is visible rather than merely slow |
| `ConvexHull` on a set with duplicate directions produces degenerate faces | Silently wrong weights near the duplicates | This set has none (checked: 8802 unique of 8802). Step 1's condition-number test catches a degenerate triangle whatever produced it |
| The poles are singular vertices with 400-face fans | Any vertex-indexed scheme is pathological there | Already why the centroid tree was chosen; recorded so it is not re-proposed |
| The 50 µs bar is measured on WSL, in scalar Python | Reads as a performance result when it is mostly call overhead | Report both numbers. The per-call overhead is roughly 20 µs of `cKDTree.query` alone regardless of `k`, which the engine pays once per block rather than once per source |

The genuine unknown is whether **barycentric weights over three vertices are
enough for the minimum-phase filters**, not just for a scalar delay. This phase
only interpolates the ITD, which is one number and provably continuous. Phase 4
applies the same weights to three complex spectra, where the failure mode is
comb filtering rather than a visible jump — and that is what the whole
ITD/minimum-phase split exists to prevent, so it should be fine. "Should be" is
why phase 5 exists.

## Out of scope for this plan

| Expected here | Actually in |
|---|---|
| The frequency-domain weighted sum of the three minimum-phase filters | [phase 4](../phase_4_block_engine.md) — it needs the prepared bank |
| `nfft`, the bank, any convolution | [phase 4](../phase_4_block_engine.md); phase 2 already fixed `nfft` at 1024 |
| Caching the hull or the tree between runs | M4. Building them costs 0.07 s, which is not worth a cache in a spike |
| Interpolating across the *time* axis, between blocks | [phase 4](../phase_4_block_engine.md)'s crossfade (D-37) — a different problem with a different answer |
| Anything under `src/` | M4, `audio/hrtf/interp.py`. Nothing here moves in |

## Outcome

**All five acceptance lines pass, none amended.** `--check` prints 46 checks
and exits zero. This is the first phase whose plan survived contact intact:
every number it predicted from the probing it did while being written held up,
including the ones it flagged as uncomfortable.

**What it got right, and why that matters here.** The probing was the point.
Rejecting the vertex-indexed scheme, choosing the exhaustive fallback over a
larger `k`, and predicting the 0.914 continuity margin were all done before any
code existed, from measurements taken while writing the plan rather than from
reasoning about what ought to be true. The 400-face pole fan in particular is
not something anyone would have guessed.

**What it got wrong.** One thing, and only in a detail: it specified the first
tier at `k = 32`, and at that size the scalar lookup came to 55 µs against a
50 µs bar. `k = 8` first is better because `cKDTree.query` costs the same at
any `k` — it is all call overhead — while the barycentric test is linear in it.
With that and an early return for the all-resolved case, the median is 42.9 µs.
Not a design error, but the plan asserted a constant it had not timed.

**Inherited by phase 4:**

| | |
|---|---|
| `triangulate(directions)` | 17 600 faces, built once in `load()`, 0.07 s |
| `locate(tri, q)` | `(face, weights, per-tier counts)`; guaranteed to resolve |
| `interpolate_itd(...)` | barycentric ITD, back in phase 2's magnitude + far-ear form |
| lookup cost | 42.9 µs for one direction, **7.5 µs per source at 32** |
| continuity | horizontal 0.914 sa / 1° · elevation 0.055 sa / 1° |

Phase 4 applies the same weights to three complex spectra instead of three
scalars. That is the genuine unknown this plan named and could not close: a
scalar delay interpolates provably continuously, and the identical weights over
minimum-phase magnitudes *should* too — that is exactly what the ITD/spectrum
split in [05](../../05-audio-engine.md) §2 exists to make true. Phase 4 builds
it; phase 5 is what says whether it worked.

One number to carry forward rather than rediscover: the ITD is interpolated
**signed**, then converted back to magnitude-plus-far-ear. Interpolating the
magnitude across the median plane would turn +30 and −30 into 30 — a delay at
full strength pointing the wrong way, where the answer is 0.
