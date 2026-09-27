# M4 · Phase 3 — Directions

**Status:** ✅ complete · **Plan:** [plans/phase_3_directions.md](plans/phase_3_directions.md)

## Goal

`audio/hrtf/lookup.py` answers "which measurements, and how much of each?"
for any direction: the triangle of the set's triangulated sphere that
contains it, and barycentric weights over its three corners (05, *3.
Spherical interpolation*). It answers for a whole block's sources in one
call, without allocating, so that phase 5 can ask it on the audio thread.
The triangle is found through a cube-map index and a walk rather than 05's
KD-tree, which allocates on every query (D-119).

## Scope

**In:** the triangulation by `scipy.spatial.ConvexHull`, built once per set;
the cube-map index, built with a centroid KD-tree off the audio thread;
the containing-triangle test and the walk; weights for a batch of
directions into preallocated arrays; the degenerate cases (a direction
exactly on an edge or a vertex, the poles); how a direction below the set's
lowest measurement is handled.

**Out:** what the weights are applied to → phases 4 and 5.

## Acceptance

- [x] Every one of SADIE II D1's 8802 directions finds itself with a weight
      of 1 on its own vertex.
- [x] For ten thousand random directions, the weights are non-negative, sum
      to 1, and reconstruct the direction from their triangle's corners.
- [x] A direction on an edge or at a pole gets a valid triangle, never none.
- [x] A batch of 32 directions is weighed with no array made inside the
      call, checked by the zero-allocation test's method.
- [x] Weighing 32 directions takes a measured fraction of a block, recorded
      in the Notes against the spike's.

## Implements

*The HRTF pipeline, 3.* in [05-audio-engine.md](../05-audio-engine.md);
S0 [phase 3](../s0_listening_spike/phase_3_interpolation.md).

## Notes

Appended while building.

**Built (2026-09-27).** SADIE II D1's hull closes with its 17 600 faces,
and the index takes 1.3 s to build. A direction takes 3.5 µs to weigh, and
32 sources about 215 µs, 2% of a block. Over ten thousand random
directions, each is rebuilt from its face's corners to within 7 × 10⁻¹⁵,
with weights summing to 1 within 2 × 10⁻¹⁶. A hundred blocks of 32 keep
nothing and raise the peak by 228 bytes: no array. The interpolated ITD
moves less than a sample a degree round the horizon and over the pole, as
S0 measured.

**Why not S0's KD-tree (D-119).** It returns new arrays on every query:
for 32 sources, 4 KB a block, twice D-106's line. A conservative index,
listing every face whose bounding cap touches a cell, was measured first.
SADIE's pole fans are wedges 10° long, and their caps put 53 candidates in
the average cell, 93 MB of table. Cells that list only what their sampled
points land in average 4.2 candidates, and a walk covers the rest. Most
queries within a degree of a pole walk, at most 8 steps. The query is plain
Python on tuples, because at nine multiplications a numpy call's
microsecond of overhead is the whole cost.

**What the tests had to learn.** The walk makes a wrong index *correct*,
just slow: routing every query through the wrong side's cells passed every
correctness test. So a test now asks the index to do its job, offering the
containing face before any walk for over 85% of directions (it offers 92%).
One mutation is equivalent by D-106's own measure. A 9-element array made
per query is about 100 bytes, under the 2 KiB line and indistinguishable
from the Python floats the query already makes. What the line exists to
catch is an array a block wide, and the tests assert that. Nine mutations;
eight caught, one after the index test was added, and one equivalent.
`blend()` exists here for phase 5, which blends the signed ITD by these
weights. The plan's ninth mutation, the ITD blended from its magnitude, is
phase 5's to test where the engine does it. The phase adds 14 tests; the
suite is 2301.
