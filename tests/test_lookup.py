"""Directions located and weighed (05, *3*; D-119). Headless.

Most sets here are synthetic: a Fibonacci sphere, and one with a pole fan
of 200 thin wedges like SADIE II D1's, so the walk is exercised without the
real set. SADIE's own checks run where it has been fetched.
"""

from __future__ import annotations

import tracemalloc

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.hrtf.decompose import itd
from immersive.audio.hrtf.lookup import Lookup
from immersive.audio.hrtf.sofa import HrirSet, builtin
from immersive.core.io.media import Refused

Directions = npt.NDArray[np.float64]


def fibonacci(count: int) -> Directions:
    index = np.arange(count) + 0.5
    z = 1.0 - 2.0 * index / count
    azimuth = np.pi * (1.0 + 5.0**0.5) * index
    ring = np.sqrt(1.0 - z * z)
    return np.column_stack([ring * np.cos(azimuth), ring * np.sin(azimuth), z])


def fanned() -> Directions:
    """A pole fanned out to a ring of 200 directions 5 degrees below it,
    over a Fibonacci sphere kept clear of the cap: SADIE's pole, smaller."""
    body = fibonacci(1500)
    body = body[body[:, 2] < np.cos(np.radians(8))]
    around = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    ring = np.column_stack(
        [
            np.sin(np.radians(5)) * np.cos(around),
            np.sin(np.radians(5)) * np.sin(around),
            np.full(200, np.cos(np.radians(5))),
        ]
    )
    return np.vstack([[[0.0, 0.0, 1.0]], ring, body])


@pytest.fixture(scope="module")
def sphere() -> tuple[Directions, Lookup]:
    directions = fibonacci(800)
    return directions, Lookup.build(directions)


@pytest.fixture(scope="module")
def fan() -> tuple[Directions, Lookup]:
    directions = fanned()
    return directions, Lookup.build(directions)


def random_directions(count: int, seed: int = 0) -> Directions:
    points = np.random.default_rng(seed).standard_normal((count, 3))
    return points / np.linalg.norm(points, axis=1, keepdims=True)


def weighed(
    lookup: Lookup, queries: Directions
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float64]]:
    vertices = np.zeros((len(queries), 3), dtype=np.int64)
    weights = np.zeros((len(queries), 3))
    lookup.weigh(np.ascontiguousarray(queries), vertices, weights)
    return vertices, weights


def assert_contained(
    directions: Directions, lookup: Lookup, queries: Directions
) -> None:
    """Every query inside its face: weights non-negative, summing to 1, and
    rebuilding the query from its three corners."""
    vertices, weights = weighed(lookup, queries)
    assert weights.min() >= -1e-9
    np.testing.assert_allclose(weights.sum(axis=1), 1.0, atol=1e-12)
    rebuilt = np.einsum("nk,nkj->nj", weights, directions[vertices])
    rebuilt /= np.linalg.norm(rebuilt, axis=1, keepdims=True)
    np.testing.assert_allclose(rebuilt, queries, atol=1e-9)


# --------------------------------------------------------------------------- #
# the triangulation
# --------------------------------------------------------------------------- #


def test_the_hull_is_closed_with_2m_minus_4_faces() -> None:
    for count in (500, 499):
        lookup = Lookup.build(fibonacci(count))
        assert lookup.faces.shape == (2 * count - 4, 3)


def test_every_inverse_undoes_its_face() -> None:
    directions = fibonacci(300)
    lookup = Lookup.build(directions)
    corners = np.transpose(directions[lookup.faces], (0, 2, 1))
    np.testing.assert_allclose(
        lookup.inverses @ corners, np.broadcast_to(np.eye(3), corners.shape), atol=1e-9
    )


def test_every_neighbour_shares_the_edge_opposite_its_corner() -> None:
    lookup = Lookup.build(fibonacci(300))
    for face, corners in enumerate(lookup.faces.tolist()):
        for corner in range(3):
            edge = {corners[(corner + 1) % 3], corners[(corner + 2) % 3]}
            other = lookup.neighbours[face, corner]
            assert edge <= set(lookup.faces[other].tolist())
            assert other != face


# --------------------------------------------------------------------------- #
# the query
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ["sphere", "fan"])
def test_every_direction_finds_itself(
    name: str, request: pytest.FixtureRequest
) -> None:
    directions, lookup = request.getfixturevalue(name)
    vertices, weights = weighed(lookup, directions)
    own = weights[vertices == np.arange(len(directions))[:, None]]
    assert own.shape == (len(directions),) and own.min() > 0.999999


@pytest.mark.parametrize("name", ["sphere", "fan"])
def test_ten_thousand_random_directions_are_each_inside_their_face(
    name: str, request: pytest.FixtureRequest
) -> None:
    directions, lookup = request.getfixturevalue(name)
    assert_contained(directions, lookup, random_directions(10_000))


def test_edges_vertices_and_poles_all_find_a_face(
    sphere: tuple[Directions, Lookup],
) -> None:
    directions, lookup = sphere
    a, b, _ = lookup.faces[17]
    edge = directions[a] + directions[b]
    queries = np.vstack(
        [edge / np.linalg.norm(edge), directions[a], [[0, 0, 1], [0, 0, -1]]]
    )
    assert_contained(directions, lookup, queries)


def test_directions_crowding_a_pole_fan_are_found_by_walking(
    fan: tuple[Directions, Lookup],
) -> None:
    """Within a degree of the pole, where each cell holds a few of 200
    wedges and most queries walk to theirs."""
    directions, lookup = fan
    rng = np.random.default_rng(3)
    near = np.column_stack([rng.uniform(-0.017, 0.017, (2000, 2)), np.ones(2000)])
    near /= np.linalg.norm(near, axis=1, keepdims=True)
    assert_contained(directions, lookup, near)


@pytest.mark.parametrize("name", ["sphere", "fan"])
def test_the_index_offers_the_right_face_before_any_walk(
    name: str, request: pytest.FixtureRequest
) -> None:
    """What the index is for: the walk makes a wrong cell *correct*, but
    slow, so correctness alone would not notice an index gone wrong.
    SADIE's cells offered the containing face for 92% of directions."""
    _, lookup = request.getfixturevalue(name)
    queries = random_directions(2000, seed=9)
    vertices, _ = weighed(lookup, queries)
    offered = 0
    for query, corners in zip(queries, vertices, strict=True):
        found = {tuple(sorted(lookup.faces[face])) for face in lookup.candidates(query)}
        offered += tuple(sorted(corners)) in found
    assert offered / len(queries) > 0.85


def test_weighing_a_block_of_32_makes_no_array(
    sphere: tuple[Directions, Lookup],
) -> None:
    """D-106's measure: nothing kept, and the peak never raised by an
    array's worth - the KD-tree's query raised it by 4 KB."""
    _, lookup = sphere
    queries = random_directions(32)
    vertices = np.zeros((32, 3), dtype=np.int64)
    weights = np.zeros((32, 3))
    itds = np.zeros(32)
    field = np.linspace(-38, 38, 800)
    lookup.weigh(queries, vertices, weights)
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        for _ in range(100):
            lookup.weigh(queries, vertices, weights)
            Lookup.blend(field, vertices, weights, itds)
        after, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert after - before <= 0
    assert peak - before < 1024


def test_blend_weighs_a_field_by_the_lookups_weights(
    sphere: tuple[Directions, Lookup],
) -> None:
    directions, lookup = sphere
    field = directions[:, 0] * 30.0
    queries = random_directions(500)
    vertices, weights = weighed(lookup, queries)
    out = np.zeros(500)
    Lookup.blend(field, vertices, weights, out)
    expected = (weights * field[vertices]).sum(axis=1)
    np.testing.assert_allclose(out, expected, atol=1e-12)


# --------------------------------------------------------------------------- #
# SADIE II D1
# --------------------------------------------------------------------------- #


def orbit(azimuths: npt.NDArray[np.float64], elevation: float = 0.0) -> Directions:
    """Project axes: azimuth from the front (+Y), clockwise to the right."""
    el = np.radians(elevation)
    az = np.radians(azimuths)
    return np.column_stack(
        [np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.full(len(az), np.sin(el))]
    )


def test_sadie_ii_d1_located_and_its_itd_continuous() -> None:
    """One test, so the set and its ITDs are made once."""
    loaded = builtin("sadie-d1")
    if isinstance(loaded, Refused):
        pytest.skip("SADIE II D1 is not fetched here: launch.py --install")
    assert isinstance(loaded, HrirSet)
    directions = loaded.directions
    lookup = Lookup.build(directions)
    assert lookup.faces.shape[0] == 17_600, "2M - 4, as S0 counted"

    vertices, weights = weighed(lookup, directions)
    own = weights[vertices == np.arange(len(directions))[:, None]]
    assert own.shape == (len(directions),) and own.min() > 0.999999
    assert_contained(directions, lookup, random_directions(10_000))

    # Continuity (S0: 0.914 samples a 1-degree step round the horizon,
    # 0.055 over the pole). The ITD is blended signed, as phase 5 will.
    field = itd(loaded.responses)
    over = np.radians(np.arange(-40.0, 181.0))  # front, up over the head, behind
    sweep = np.column_stack([np.zeros(len(over)), np.cos(over), np.sin(over)])
    for path in (orbit(np.arange(0.0, 360.0, 1.0)), sweep):
        vertices, weights = weighed(lookup, path)
        blended = np.zeros(len(path))
        Lookup.blend(field, vertices, weights, blended)
        assert np.abs(np.diff(blended)).max() < 1.0


def test_an_index_keeps_its_own_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Built at one size and queried after the constant changed - as a
    cached index read by a later version would be. It used to read the
    constant at query time and run past its own table."""
    from immersive.audio.hrtf import lookup as module

    directions = fibonacci(300)
    monkeypatch.setattr(module, "CELLS", 16)
    small = Lookup.build(directions)
    monkeypatch.undo()
    assert small.resolution == 16 and module.CELLS == 64
    assert_contained(directions, small, random_directions(2000))


def test_cells_that_do_not_fit_their_resolution_are_refused(
    sphere: tuple[Directions, Lookup],
) -> None:
    _, lookup = sphere
    with pytest.raises(ValueError, match="resolution"):
        Lookup.assemble(
            lookup.faces,
            lookup.inverses,
            lookup.neighbours,
            lookup.cells,
            lookup.offsets,
            lookup.resolution + 1,
        )
