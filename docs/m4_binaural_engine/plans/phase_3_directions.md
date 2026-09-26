# Plan — M4 · Phase 3 — Directions

**Written:** 2026-09-27 · **Status:** ✅ complete

## Approach

`audio/hrtf/lookup.py`, a `Lookup` built once per set and queried every
block (D-119).

**The triangulation.** `scipy.spatial.ConvexHull` over the set's directions.
It is checked closed, with exactly `2M − 4` faces (S0: 17 600 for SADIE II
D1). Each face keeps its vertices as columns of a 3 × 3 matrix and that
matrix's inverse, so `inverse @ q` is the barycentric coordinate of `q`,
inside when all three are non-negative. Each face also keeps its neighbour
across the edge opposite each vertex.

**The index.** A cube map, 64 × 64 cells a face. Each cell lists the faces
that contain any of 4 × 4 points sampled inside it, found at build time
with S0's tiered KD-tree search (8, 32, 128, then every face), which may
allocate: it runs once, on a worker.

**The query**, `weigh(directions, vertices, weights)`: for each source, the
cell by arithmetic on its largest component, then the cell's candidates
tested in plain Python on precomputed tuples. Failing those, a walk from the
best of them across the edge opposite its most negative weight, until all
three are non-negative. The results go into the caller's preallocated
arrays: vertex indices, and weights normalised to sum to 1. Nothing is
made that outlives the call, and no array is made at all.

**A bound on the walk.** It ends on a spherical Delaunay triangulation, and
the convex hull of points on a sphere is one. It is still bounded, by the
face count: never reached, and if it ever were, the best face's weights
clamped and renormalised rather than the audio thread held.

## Decisions settled here

**D-119**, how a direction is located. The KD-tree allocates on every
query, and a conservative index was 93 MB. So: sampled cells, and a walk.

## Steps

1. **The triangulation and the index.** `Lookup.build(directions)`: the
   hull, its inverses and neighbours, the cube map. Tests:
   - `2M − 4` faces, and a set with a missing direction still closes;
   - every face's inverse reconstructs its vertices;
   - every neighbour pair shares an edge.
2. **The query.** `weigh()`. Tests:
   - every one of SADIE II D1's directions finds itself with a weight of
     1 on its own vertex;
   - ten thousand random directions give non-negative weights that sum to
     1 and rebuild the direction;
   - a point on an edge, on a vertex and at each pole gets a valid face;
   - two thousand directions within a degree of a pole, where most walk,
     are all found;
   - the zero-allocation test's method finds no array made over a hundred
     batches of 32.
3. **Continuity and cost.** Along a 1° horizontal orbit and an elevation
   sweep over the pole, the interpolated ITD moves less than a sample a
   step, as S0 measured (0.914 and 0.055). Weighing 32 directions is timed
   and recorded.

## Files

`src/immersive/audio/hrtf/lookup.py` — new: `Lookup`
`tests/test_lookup.py` — new

## Mutations, named before the tests

| # | Mutation | Expected to be caught by |
|---|---|---|
| 1 | a negative weight accepted (tolerance −0.1) | non-negative weights over 10 000 |
| 2 | weights not normalised | weights sum to 1 |
| 3 | the walk crosses the wrong edge (the most positive weight's) | 2 000 near the pole all found |
| 4 | no walk: the best candidate returned as it is | 2 000 near the pole all found |
| 5 | the cube map's axis chosen by the first component, not the largest | 10 000 random, all found |
| 6 | a cell's sign mishandled (the −axis faces read as +) | 10 000 random, all found |
| 7 | an allocating product (`inverse @ q`) in the query | no array made |
| 8 | the vertex indices of the wrong face written | every direction finds itself |
| 9 | the ITD interpolated from its magnitude | continuity across the median plane |

## Risks and unknowns

- **Python speed.** At about 4 candidates and the odd walk step, 32 sources
  should cost a few hundred microseconds a block, 3% of the budget. If a
  set denser than SADIE makes that worse, the index grows finer rather
  than the query slower.
- **Build time**, about 1.2 s for SADIE. It runs on a worker and phase 4
  caches it, with the bank.

## Out of scope for this plan

| Not here | Where |
|---|---|
| Weighting the bank's filters and the ITDs | phase 5, from what `weigh` returns |
| Caching the index | phase 4 |

## Outcome

Built as planned, faster than the plan feared: 3.5 µs a direction against
the prototype's 10.8, once the query was plain Python on tuples. The plan
missed one test, the index doing its job, which it only learned when a
broken index passed on the walk's back. It named one mutation (the
allocating product) that D-106's own measure cannot tell from a float, and
one (the ITD's magnitude) that belongs to phase 5.

What phase 4 needs: `Lookup.build(directions)`, 1.3 s for SADIE, to cache
with the decomposition and the bank. What phase 5 needs: `weigh()` and
`blend()` into preallocated arrays, every block.
