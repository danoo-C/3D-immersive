"""Which measurements, and how much of each, for any direction (05, *3.
Spherical interpolation*; D-119).

The set's directions are triangulated once, by their convex hull. A query
direction is inside the triangle whose barycentric coordinates for it are
all non-negative, and those coordinates, normalised to sum to 1, are the
weights over its three measurements.

**Finding the triangle without allocating.** 05 names a KD-tree over face
centroids, and S0 used one. But `cKDTree.query` makes new arrays on every
call, and the audio thread asks every block (D-106). So a cube map indexes
the sphere instead, 64 by 64 cells a face. Each cell lists the faces that
contain any of 16 points sampled in it, found once with the KD-tree, off
the audio thread. A query tests its cell's few candidates in plain Python
arithmetic on precomputed tuples; at this size that is faster than numpy's
per-call overhead, and the floats it makes are freed at once. A query in
none of them walks from the best across the edge opposite its most negative
weight until all three are non-negative. On the convex hull of points on a
sphere - their spherical Delaunay triangulation - such a walk ends at the
containing face. SADIE II D1: 4.2 candidates a cell, and at most 8 steps,
next to a pole.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from scipy.spatial import ConvexHull, cKDTree

#: Cells along each edge of each of the cube map's six faces.
CELLS: Final = 64

#: Points sampled along each edge of a cell to find its candidates.
SAMPLES: Final = 4

#: A barycentric coordinate this far below zero still counts as inside:
#: rounding on a shared edge, never a real miss (S0: sums within 2.2e-16).
INSIDE: Final = -1e-9

#: The tiers of the build's KD-tree search, then every face (S0 phase 3:
#: 8 resolves 83% of directions, 32 99%, 128 all but one in five thousand).
TIERS: Final = (8, 32, 128)


@dataclass(frozen=True, eq=False)
class Lookup:
    """A set's triangulated sphere, indexed for queries on the audio thread."""

    #: `[F, 3]` the vertex indices of each face.
    faces: npt.NDArray[np.int64]
    #: `[F, 3, 3]` each face's vertex matrix, inverted.
    inverses: npt.NDArray[np.float64]
    #: `[F, 3]` the face across the edge opposite each vertex.
    neighbours: npt.NDArray[np.int64]
    #: The same three, as tuples, for the query's plain arithmetic.
    _faces: tuple[tuple[int, int, int], ...]
    _inverses: tuple[tuple[float, ...], ...]
    _neighbours: tuple[tuple[int, int, int], ...]
    #: Each cube-map cell's candidate faces.
    _cells: tuple[tuple[int, ...], ...]

    @classmethod
    def build(cls, directions: npt.NDArray[np.float64]) -> Lookup:
        """Triangulate `directions`, unit vectors, and index the result.
        Allocates freely: a worker's job, once per set."""
        faces = np.ascontiguousarray(ConvexHull(directions).simplices, dtype=np.int64)
        vertices = directions[faces]  # [F, 3 vertices, 3 components]
        inverses = np.linalg.inv(np.transpose(vertices, (0, 2, 1)))
        neighbours = _neighbours(faces)
        centroids = vertices.sum(axis=1)
        centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
        tree = cKDTree(centroids)
        cells = tuple(
            tuple(int(face) for face in np.unique(row))
            for row in _located(_samples(), inverses, tree)
        )
        return cls(
            faces=faces,
            inverses=inverses,
            neighbours=neighbours,
            _faces=tuple((int(a), int(b), int(c)) for a, b, c in faces.tolist()),
            _inverses=tuple(tuple(row) for row in inverses.reshape(-1, 9).tolist()),
            _neighbours=tuple(
                (int(a), int(b), int(c)) for a, b, c in neighbours.tolist()
            ),
            _cells=cells,
        )

    def weigh(
        self,
        directions: npt.NDArray[np.float64],
        vertices: npt.NDArray[np.int64],
        weights: npt.NDArray[np.float64],
        count: int | None = None,
    ) -> None:
        """For each of the first `count` rows of `directions`, unit vectors,
        write its face's three vertex indices into `vertices` and their
        weights, summing to 1, into `weights`. No array is made."""
        rows = directions.shape[0] if count is None else count
        for row in range(rows):
            x = float(directions[row, 0])
            y = float(directions[row, 1])
            z = float(directions[row, 2])
            face, a, b, c = self._locate(x, y, z)
            total = a + b + c
            first, second, third = self._faces[face]
            vertices[row, 0] = first
            vertices[row, 1] = second
            vertices[row, 2] = third
            weights[row, 0] = a / total
            weights[row, 1] = b / total
            weights[row, 2] = c / total

    def candidates(self, direction: npt.NDArray[np.float64]) -> tuple[int, ...]:
        """The faces the index offers for `direction`, before any walk."""
        return self._cells[_cell(*(float(x) for x in direction))]

    @staticmethod
    def blend(
        field: npt.NDArray[np.float64],
        vertices: npt.NDArray[np.int64],
        weights: npt.NDArray[np.float64],
        out: npt.NDArray[np.float64],
        count: int | None = None,
    ) -> None:
        """A per-direction scalar - the ITD - at each weighed direction, into
        `out`. The field must be signed where it has a sign (phase 2): a
        blend of magnitudes across the median plane points the wrong way."""
        rows = vertices.shape[0] if count is None else count
        for row in range(rows):
            out[row] = (
                float(weights[row, 0]) * float(field[vertices[row, 0]])
                + float(weights[row, 1]) * float(field[vertices[row, 1]])
                + float(weights[row, 2]) * float(field[vertices[row, 2]])
            )

    def _locate(self, x: float, y: float, z: float) -> tuple[int, float, float, float]:
        """The face containing `(x, y, z)` and its barycentric coordinates."""
        best = -1
        best_low = -2.0
        for face in self._cells[_cell(x, y, z)]:
            a, b, c = self._coordinates(face, x, y, z)
            low = min(a, b, c)
            if low >= INSIDE:
                return face, a, b, c
            if low > best_low:
                best, best_low = face, low
        # The walk: across the edge opposite the most negative coordinate.
        face = best
        for _ in range(len(self._faces)):
            a, b, c = self._coordinates(face, x, y, z)
            if a >= INSIDE and b >= INSIDE and c >= INSIDE:
                return face, a, b, c
            opposite = 0 if a <= b and a <= c else (1 if b <= c else 2)
            face = self._neighbours[face][opposite]
        # Unreachable on a closed hull; never hold the audio thread for it.
        a, b, c = self._coordinates(face, x, y, z)
        return face, max(a, 0.0), max(b, 0.0), max(c, 0.0) or 1e-12

    def _coordinates(
        self, face: int, x: float, y: float, z: float
    ) -> tuple[float, float, float]:
        m = self._inverses[face]
        return (
            m[0] * x + m[1] * y + m[2] * z,
            m[3] * x + m[4] * y + m[5] * z,
            m[6] * x + m[7] * y + m[8] * z,
        )


def _cell(x: float, y: float, z: float) -> int:
    """The cube-map cell `(x, y, z)` falls in: its largest component picks
    the cube face and its sign, and the other two, divided by it, the cell."""
    ax, ay, az = abs(x), abs(y), abs(z)
    if ax >= ay and ax >= az:
        axis, major, u, v = 0, x, y, z
    elif ay >= az:
        axis, major, u, v = 1, y, z, x
    else:
        axis, major, u, v = 2, z, x, y
    side = 2 * axis + (0 if major > 0 else 1)
    scale = abs(major)
    i = min(int((u / scale + 1.0) * 0.5 * CELLS), CELLS - 1)
    j = min(int((v / scale + 1.0) * 0.5 * CELLS), CELLS - 1)
    return (side * CELLS + i) * CELLS + j


def _samples() -> npt.NDArray[np.float64]:
    """`[6 * CELLS * CELLS, SAMPLES * SAMPLES, 3]`: the points sampled in
    each cell, in `_cell`'s order."""
    grid = (np.arange(CELLS * SAMPLES) + 0.5) / (CELLS * SAMPLES) * 2.0 - 1.0
    u, v = np.meshgrid(grid, grid, indexing="ij")
    sides = []
    for axis in range(3):
        for sign in (1.0, -1.0):
            points = np.empty((*u.shape, 3))
            points[..., axis] = sign
            points[..., (axis + 1) % 3] = u
            points[..., (axis + 2) % 3] = v
            points /= np.linalg.norm(points, axis=-1, keepdims=True)
            per_cell = points.reshape(CELLS, SAMPLES, CELLS, SAMPLES, 3)
            sides.append(
                per_cell.transpose(0, 2, 1, 3, 4).reshape(CELLS * CELLS, SAMPLES**2, 3)
            )
    return np.concatenate(sides)


def _located(
    samples: npt.NDArray[np.float64],
    inverses: npt.NDArray[np.float64],
    tree: cKDTree,
) -> npt.NDArray[np.int64]:
    """The face containing each sample, by S0's tiered search: the nearest
    centroids first, then more, then every face - which on a closed hull
    cannot miss."""
    points = samples.reshape(-1, 3)
    found = np.full(points.shape[0], -1, dtype=np.int64)
    pending = np.arange(points.shape[0])
    faces = inverses.shape[0]
    for k in (*TIERS, faces):
        if pending.size == 0:
            break
        _, near = tree.query(points[pending], k=min(k, faces))
        near = near.reshape(pending.size, -1)
        coordinates = np.einsum("nkij,nj->nki", inverses[near], points[pending])
        inside = (coordinates >= INSIDE).all(axis=-1)
        hit = inside.any(axis=1)
        found[pending[hit]] = near[hit, inside[hit].argmax(axis=1)]
        pending = pending[~hit]
    return found.reshape(samples.shape[:2])


def _neighbours(faces: npt.NDArray[np.int64]) -> npt.NDArray[np.int64]:
    """For each face, the face across the edge opposite each vertex."""
    across = np.full(faces.shape, -1, dtype=np.int64)
    edges: dict[tuple[int, int], tuple[int, int]] = {}
    for face, (a, b, c) in enumerate(faces.tolist()):
        for corner, (p, q) in enumerate(((b, c), (c, a), (a, b))):
            key = (p, q) if p < q else (q, p)
            other = edges.pop(key, None)
            if other is None:
                edges[key] = (face, corner)
            else:
                across[face, corner] = other[0]
                across[other[0], other[1]] = face
    return across
