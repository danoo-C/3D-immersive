# S0 · Phase 3 — Spherical interpolation

**Status:** not started · **Plan:** not written yet —
`plans/phase_3_interpolation.md`

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

- [ ] For 10 000 pseudo-random directions with a fixed seed: every query finds a
      containing triangle, weights sum to 1.0 within 1e-6, and no weight is
      below −1e-9. A closed hull has no gaps, so a miss means the candidate
      search is too narrow, not that the direction is unreachable.
- [ ] Querying exactly at a measurement direction returns that vertex with a
      weight above 0.999.
- [ ] Continuity along a 1°-stepped horizontal orbit: the interpolated ITD
      changes by less than one sample between adjacent steps, with no jump at a
      triangle boundary. Printed as a max-step figure.
- [ ] The same check across an elevation sweep from −40° through overhead to
      the other side, where triangles are largest and sparsest.
- [ ] Median lookup time printed and under 50 µs. It runs per block; if it is
      slow here it will be slow in the engine.

## Implements

§3 *Spherical interpolation* of [05-audio-engine.md](../05-audio-engine.md).

## Notes

Appended while building.
