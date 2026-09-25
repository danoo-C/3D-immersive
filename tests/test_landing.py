"""Where a drop from the pool lands, and what it does: no window, no Qt."""

from __future__ import annotations

import copy

import pytest

from immersive.core.commands import UndoStack
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Project,
    SnapSetting,
    validate,
)
from immersive.core.time import SAMPLE_RATE, Division
from immersive.ui.timeline.landing import dropped, edges, landing
from immersive.ui.timeline.metrics import LANE_HEIGHT

#: 480 samples a pixel; at 120 BPM a sixteenth is 6 000 samples, 12.5 px.
SCALE = 480.0
PALETTE = ("#A855F7", "#22D3EE", "#F59E0B")

KICK = MediaFile("m-00000001", "kick.wav", "kick.wav", SAMPLE_RATE, 1, 30_000)
PAD = MediaFile("m-00000002", "pad.wav", "pad.wav", SAMPLE_RATE, 2, 100_000)


def a_project(*clips_on_first: Clip) -> Project:
    return Project(
        media_pool=[KICK, PAD],
        channels=[
            Channel("c-00000001", "A", "#A855F7", clips=list(clips_on_first)),
            Channel("c-00000002", "B", "#22D3EE"),
        ],
    )


def lane(n: int) -> float:
    """A y in the middle of lane `n`."""
    return n * LANE_HEIGHT + LANE_HEIGHT / 2


# --------------------------------------------------------------------------- #
# where
# --------------------------------------------------------------------------- #


def test_a_drop_lands_on_the_lane_under_it_at_the_snapped_sample() -> None:
    where = landing(a_project(), [KICK.id], x=110, y=lane(1), scale=SCALE)

    assert where is not None
    assert where.lane == 1 and not where.creates
    assert 110 * SCALE == 52_800
    assert where.start == 54_000, "the nearest sixteenth, not the raw sample"


def test_alt_lands_exactly_under_the_pointer() -> None:
    where = landing(a_project(), [KICK.id], x=110, y=lane(0), scale=SCALE, exact=True)
    assert where is not None and where.start == 52_800


def test_an_edge_on_another_channel_is_a_snap_target() -> None:
    """F-17: lining up with the channel above is what snapping to edges is for."""
    project = a_project(Clip("k-00000001", KICK.id, 22_900, 0, 30_000))  # ends 52 900
    where = landing(project, [KICK.id], x=110, y=lane(1), scale=SCALE)
    assert where is not None and where.start == 52_900
    assert edges(project) == [22_900, 52_900]


def test_the_target_channels_own_snap_is_used() -> None:
    project = a_project()
    project.channels[1].snap_override = SnapSetting(division=Division.QUARTER)
    where = landing(project, [KICK.id], x=110, y=lane(1), scale=SCALE)
    assert where is not None and where.start == 48_000, "the nearest quarter"


def test_a_channel_that_snaps_to_nothing_lands_exactly() -> None:
    project = a_project()
    project.channels[0].snap_override = SnapSetting(enabled=False)
    where = landing(project, [KICK.id], x=110, y=lane(0), scale=SCALE)
    assert where is not None and where.start == 52_800


def test_several_samples_go_end_to_end_in_the_pools_order() -> None:
    where = landing(a_project(), [PAD.id, KICK.id], x=0, y=lane(0), scale=SCALE)
    assert where is not None
    assert [(sample.id, start) for sample, start in where.placed] == [
        (PAD.id, 0),
        (KICK.id, 100_000),
    ]
    assert where.end == 130_000


def test_below_the_last_lane_a_drop_makes_a_channel() -> None:
    where = landing(a_project(), [KICK.id], x=0, y=lane(5), scale=SCALE)
    assert where is not None and where.creates and where.lane == 2


def test_something_that_is_not_the_projects_sample_does_not_land() -> None:
    assert landing(a_project(), ["m-deadbeef"], x=0, y=lane(0), scale=SCALE) is None
    assert landing(a_project(), [], x=0, y=lane(0), scale=SCALE) is None


# --------------------------------------------------------------------------- #
# whether
# --------------------------------------------------------------------------- #


def test_shift_refuses_a_drop_that_would_overlap() -> None:
    project = a_project(Clip("k-00000001", KICK.id, 50_000, 0, 30_000))
    where = landing(
        project, [KICK.id], x=100, y=lane(0), scale=SCALE, refuse_overlap=True
    )
    assert where is not None and where.refused


def test_shift_does_not_refuse_a_drop_into_space() -> None:
    project = a_project(Clip("k-00000001", KICK.id, 500_000, 0, 30_000))
    where = landing(
        project, [KICK.id], x=0, y=lane(0), scale=SCALE, refuse_overlap=True
    )
    assert where is not None and not where.refused


def test_a_drop_that_ends_where_a_clip_begins_is_no_overlap() -> None:
    project = a_project(Clip("k-00000001", KICK.id, 30_000, 0, 30_000))
    where = landing(
        project, [KICK.id], x=0, y=lane(0), scale=SCALE, exact=True, refuse_overlap=True
    )
    assert where is not None and not where.refused


# --------------------------------------------------------------------------- #
# what
# --------------------------------------------------------------------------- #


def test_a_drop_is_one_command_and_undo_takes_it_back() -> None:
    project = a_project(Clip("k-00000001", KICK.id, 10_000, 0, 30_000))
    before = copy.deepcopy(project)
    stack = UndoStack(project)
    where = landing(project, [PAD.id, KICK.id], x=0, y=lane(0), scale=SCALE, exact=True)
    assert where is not None

    stack.push(dropped(project, where, PALETTE))

    assert [(c.media_id, c.start, c.length) for c in project.channels[0].clips] == [
        (PAD.id, 0, 100_000),
        (KICK.id, 100_000, 30_000),
    ]
    assert validate(project) == []
    stack.undo()
    assert project == before


def test_a_drop_below_the_last_lane_makes_one_channel_holding_every_sample() -> None:
    project = a_project()
    before = copy.deepcopy(project)
    stack = UndoStack(project)
    where = landing(project, [PAD.id, KICK.id], x=0, y=lane(9), scale=SCALE)
    assert where is not None

    stack.push(dropped(project, where, PALETTE))

    assert len(project.channels) == 3
    assert [clip.media_id for clip in project.channels[2].clips] == [PAD.id, KICK.id]
    assert project.channels[2].color == PALETTE[2]
    stack.undo()
    assert project == before


@pytest.mark.parametrize("count", [1, 3])
def test_every_dropped_clip_has_an_id_of_its_own(count: int) -> None:
    project = a_project()
    where = landing(project, [KICK.id] * count, x=0, y=lane(0), scale=SCALE)
    assert where is not None
    command = dropped(project, where, PALETTE)
    command.do()
    assert validate(project) == []
