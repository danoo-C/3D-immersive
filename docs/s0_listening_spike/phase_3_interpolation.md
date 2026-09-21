# S0 · Phase 3 — Spherical interpolation

**Status:** ✅ complete · **Plan:**
[plans/phase_3_interpolation.md](plans/phase_3_interpolation.md)

## Goal

Given any query direction, return the three surrounding measurement indices and
their barycentric weights, fast enough to run once per source per block. After
this phase the spike can produce a filter for a direction that was never
measured, which is the whole point of a moving source.

## Scope

**In:** `scipy.spatial.ConvexHull` over the unit vectors; a `cKDTree` over face
centroids for candidate selection; an exact barycentric containment test over
the nearest few faces; the weighted sum of the three scalar ITDs from
[phase 2](phase_2_itd_minimum_phase.md).

**Out:** the frequency-domain weighted sum of the minimum-phase filters, which
needs the prepared bank and belongs to
[phase 4](phase_4_block_engine.md). Any caching of the hull or the tree → M4.

## Acceptance

- [x] For 10 000 pseudo-random directions with a fixed seed: every query finds a
      containing triangle, weights sum to 1.0 within 1e-6, and no weight is
      below −1e-9. A closed hull has no gaps, so a miss means the candidate
      search is too narrow, not that the direction is unreachable.
- [x] Querying exactly at a measurement direction returns that vertex with a
      weight above 0.999.
- [x] Continuity along a 1°-stepped horizontal orbit: the interpolated ITD
      changes by less than one sample between adjacent steps, with no jump at a
      triangle boundary. Printed as a max-step figure.
- [x] The same check across an elevation sweep from −40° through overhead to
      the other side, where triangles are largest and sparsest.
- [x] Median lookup time printed and under 50 µs. It runs per block; if it is
      slow here it will be slow in the engine.

## Implements

§3 *Spherical interpolation* of [05-audio-engine.md](../05-audio-engine.md).

## Notes

**Done. All five acceptance lines pass, none of them amended.**

```
triangles    17600 faces over 8802 directions (2M-4 = 17600)
continuity   horizontal 1 deg: max step 0.914 samples
             elevation sweep:  max step 0.055 samples
```

**The triangulation is exact rather than approximate.** 17 600 faces is
precisely `2M − 4`, the Euler characteristic of a closed triangulated sphere,
so no measurement was swallowed as interior and there are no gaps. That is
what makes "every direction is inside some triangle" a geometric fact and not
a hope, and it is asserted rather than assumed. Worst face condition number is
8 961 — no degenerate triangles, which a set with duplicate directions would
have produced.

**Containment by one 3×3 solve.** Solving `M @ [a,b,c] = q` with the
triangle's vertices as columns gives the barycentric coordinate directly, and
`q` is inside iff all three are non-negative. Weights sum to 1 within
**2.2e-16** over 10 000 directions. No ray-plane intersection, no spherical
trigonometry, nothing that needs a special case at a pole.

⚠️ **The candidate search needed a guarantee, not a bigger `k`.** The phase
scope says "a `cKDTree` over face centroids … over the nearest few faces", and
a centroid tree alone does not get there: k=8 resolves 83%, k=32 resolves
98.95%, k=128 resolves 100% *of one seed's ten thousand directions* — which is
not the same claim as the acceptance's "every query finds a containing
triangle". So the tiers run 8 → 32 → 128 and then test **every face**. On a
closed hull that cannot fail, so the guarantee comes from geometry rather than
from a constant that happened to be large enough. Measured over 10 000
directions: `k=8: 8303, k=32: 1529, k=128: 166, every face: 2`. The exhaustive
tier ran twice in ten thousand, and it is the reason the line is true.

**Rejected on measurement: indexing faces by vertex.** Each pole is a single
measurement fanning out to a whole ring, so **one vertex touches 400 faces**.
A padded vertex→faces table ran at 40 µs for one nearest vertex — and still
only 99.92%, because the containing triangle need not touch the nearest vertex
— and 112 µs for two. Worse on both axes than the centroid tree.

**Continuity holds, with the margin the plan warned about.** The horizontal
orbit's worst 1° step is **0.914 samples** against a limit of 1.0. The
elevation sweep, through the sparsest triangles and over the pole, is 0.055.
Crossing a triangle boundary is **no worse than staying inside one** (0.914
across 338 crossings against 0.760 within), which is what "no jump at a
triangle boundary" has to mean — barycentric interpolation is continuous
across a shared edge by construction, and this is the measurement that says so
rather than the argument.

The 0.914 is roughly twice the smooth sine-law slope at that azimuth, so about
half of it is roughness in the measured ITD field rather than anything the
interpolation did. A coarser dataset would fail this line, and the question
then would be the grid, not this code.

**Timing, and which number means anything.** Median **42.9 µs** for a single
direction, against the 50 µs the acceptance asks for. Getting there took two
changes, both worth recording:

- The first tier is 8, not 32. `cKDTree.query` costs 13–14 µs whichever it is
  — essentially all call overhead — while the barycentric test is linear in
  `k`, so the 84% that resolve at 8 pay a quarter of the arithmetic.
- `locate` returns early when everything resolves in the first tier, skipping
  the scatter bookkeeping that manages partial results. On a single direction
  that bookkeeping cost more than the arithmetic it exists to manage.

⚠️ Roughly three quarters of that 42.9 µs is `cKDTree.query` call overhead,
which the engine pays **once per block**, not once per source. The figure that
predicts M4 is the batched one: **7.5 µs per source at 32 sources**, or about
240 µs of a 10.7 ms block — a little over 2%. The scalar number is the one the
acceptance names; the batched number is the one worth carrying forward.
