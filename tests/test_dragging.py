"""Where a drag on clips lands, and how it snaps: no window, no Qt."""

from __future__ import annotations

import pytest

from immersive.core.edits import Edge
from immersive.core.model import Channel, Clip, MediaFile, Project, SnapSetting
from immersive.core.time import SAMPLE_RATE, Division
from immersive.ui.timeline.dragging import (
    EDGE,
    Part,
    lanes_moved,
    part_at,
    snapped_move,
    snapped_trim,
    targets,
)
from immersive.ui.timeline.metrics import LANE_HEIGHT

#: At 120 BPM in 4/4 a sixteenth is 6 000 samples.
SIXTEENTH = 6_000
LONG = MediaFile("m-00000001", "long.wav", "long.wav", SAMPLE_RATE, 1, 10_000_000)


def clip(start: int, length: int, identifier: str) -> Clip:
    return Clip(identifier, LONG.id, start, 0, length)


def project(*rows: list[Clip]) -> Project:
    return Project(
        media_pool=[LONG],
        channels=[
            Channel(f"c-0000000{n + 1}", f"C{n}", "#A855F7", clips=list(row))
            for n, row in enumerate(rows)
        ],
    )


# --------------------------------------------------------------------------- #
# what a press takes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("x", "part"),
    [
        (0, Part.START),
        (EDGE - 0.5, Part.START),
        (EDGE, Part.BODY),
        (100 - EDGE - 0.5, Part.BODY),
        (100 - EDGE, Part.END),
        (99.5, Part.END),
    ],
)
def test_a_wide_clip_has_an_edge_zone_at_each_end(x: float, part: Part) -> None:
    assert part_at(x, 100) is part


def test_a_narrow_clip_keeps_a_third_of_itself_to_move_by() -> None:
    assert [part_at(x, 9) for x in (2.9, 3, 5.9, 6)] == [
        Part.START,
        Part.BODY,
        Part.BODY,
        Part.END,
    ]


def test_a_part_names_the_edge_a_trim_from_it_moves() -> None:
    assert (Part.START.edge, Part.END.edge, Part.BODY.edge) == (
        Edge.START,
        Edge.END,
        None,
    )


def test_lanes_are_counted_from_the_lane_pressed_in() -> None:
    near_top = LANE_HEIGHT + 2
    assert lanes_moved(near_top, near_top + LANE_HEIGHT - 3) == 0
    assert lanes_moved(near_top, 3 * LANE_HEIGHT + 1) == 2
    assert lanes_moved(near_top, LANE_HEIGHT - 1) == -1


# --------------------------------------------------------------------------- #
# targets
# --------------------------------------------------------------------------- #


def test_the_dragged_clips_edges_are_not_targets() -> None:
    moved, still = clip(0, 10_000, "k-00000001"), clip(20_000, 5_000, "k-00000002")
    arrangement = project([moved, still])
    assert targets(arrangement, [moved]) == [20_000, 25_000]


def test_a_trim_leaves_out_only_the_edge_it_moves() -> None:
    trimmed, still = clip(0, 10_000, "k-00000001"), clip(20_000, 5_000, "k-00000002")
    arrangement = project([trimmed, still])
    assert targets(arrangement, [trimmed], Edge.END) == [0, 20_000, 25_000]
    assert targets(arrangement, [trimmed], Edge.START) == [10_000, 20_000, 25_000]


# --------------------------------------------------------------------------- #
# a move
# --------------------------------------------------------------------------- #


def moved(
    arrangement: Project,
    grabbed: Clip,
    delta: int,
    *,
    lanes: int = 0,
    exact: bool = False,
) -> int:
    return snapped_move(
        arrangement,
        grabbed,
        0,
        delta,
        lanes,
        targets(arrangement, [grabbed]),
        exact=exact,
    )


def test_a_move_snaps_the_start_to_the_grid() -> None:
    grabbed = clip(0, 10_000, "k-00000001")  # its end on no grid line
    assert moved(project([grabbed]), grabbed, 6_500) == SIXTEENTH


def test_a_move_snaps_the_end_to_a_neighbour_when_that_is_nearer() -> None:
    grabbed = clip(0, 10_000, "k-00000001")
    neighbour = clip(25_000, 5_000, "k-00000002")
    arrangement = project([grabbed, neighbour])
    # start 14 600 is 2 600 from the grid; end 24 600 is 400 from 25 000
    assert moved(arrangement, grabbed, 14_600) == 15_000


def test_a_move_snaps_the_start_when_that_is_nearer() -> None:
    grabbed = clip(0, 10_000, "k-00000001")
    neighbour = clip(25_000, 5_000, "k-00000002")
    arrangement = project([grabbed, neighbour])
    # start 12 300 is 300 from the grid; end 22 300 is 2 700 from 25 000
    assert moved(arrangement, grabbed, 12_300) == 2 * SIXTEENTH


def test_a_small_move_does_not_snap_back_to_where_it_began() -> None:
    grabbed = clip(13_000, 10_000, "k-00000001")  # placed off the grid
    assert moved(project([grabbed]), grabbed, 1_500) == -1_000, "to 12 000"


def test_a_move_snaps_by_the_lane_it_lands_in() -> None:
    grabbed = clip(0, 10_000, "k-00000001")
    arrangement = project([grabbed], [], [])
    arrangement.channels[1].snap_override = SnapSetting(enabled=False)
    arrangement.channels[2].snap_override = SnapSetting(division=Division.QUARTER)

    assert moved(arrangement, grabbed, 6_500, lanes=1) == 6_500, "off there"
    assert moved(arrangement, grabbed, 6_500, lanes=2) == 0, "a quarter is 24 000"
    assert moved(arrangement, grabbed, 6_500, lanes=9) == 0, "the last lane's"


def test_alt_moves_exactly() -> None:
    grabbed = clip(0, 10_000, "k-00000001")
    assert moved(project([grabbed]), grabbed, 6_500, exact=True) == 6_500


def test_snapping_off_for_the_project_moves_exactly() -> None:
    grabbed = clip(0, 10_000, "k-00000001")
    arrangement = project([grabbed])
    arrangement.snap = SnapSetting(enabled=False)
    assert moved(arrangement, grabbed, 6_500) == 6_500


# --------------------------------------------------------------------------- #
# a trim
# --------------------------------------------------------------------------- #


def trim(
    arrangement: Project, trimmed: Clip, edge: Edge, delta: int, *, exact: bool = False
) -> int:
    return snapped_trim(
        arrangement,
        trimmed,
        arrangement.channels[0],
        edge,
        delta,
        targets(arrangement, [trimmed], edge),
        exact=exact,
    )


def test_a_trimmed_end_snaps_to_the_grid() -> None:
    trimmed = clip(0, 10_000, "k-00000001")
    assert trim(project([trimmed]), trimmed, Edge.END, 3_000) == 2_000, "to 12 000"


def test_a_trimmed_edge_snaps_to_a_neighbour_when_that_is_nearer() -> None:
    trimmed = clip(0, 10_000, "k-00000001")
    neighbour = clip(25_000, 5_000, "k-00000002")
    arrangement = project([trimmed, neighbour])
    assert trim(arrangement, trimmed, Edge.END, 14_700) == 15_000


def test_a_trimmed_start_snaps_by_its_channel() -> None:
    trimmed = clip(30_000, 10_000, "k-00000001")
    arrangement = project([trimmed])
    assert trim(arrangement, trimmed, Edge.START, -3_500) == -6_000
    arrangement.channels[0].snap_override = SnapSetting(division=Division.QUARTER)
    assert trim(arrangement, trimmed, Edge.START, -3_500) == -6_000, "to 24 000"
    assert trim(arrangement, trimmed, Edge.START, -1_000) == -6_000
    arrangement.channels[0].snap_override = SnapSetting(enabled=False)
    assert trim(arrangement, trimmed, Edge.START, -3_500) == -3_500


def test_alt_trims_exactly() -> None:
    trimmed = clip(0, 10_000, "k-00000001")
    assert trim(project([trimmed]), trimmed, Edge.END, 3_000, exact=True) == 3_000
