"""Samples, seconds, bars:beats and snapping.

No Qt, no audio device, no `Project` — this module takes numbers.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from immersive.core.curves import Curve, Keyframe
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Project,
    SnapSetting,
    effective_snap,
)
from immersive.core.time import (
    SAMPLE_RATE,
    TICKS_PER_BEAT,
    BarBeat,
    Division,
    division_ticks,
    from_bar_beat,
    from_seconds,
    grid_step,
    samples_per_bar,
    samples_per_beat,
    snap,
    to_bar_beat,
    to_seconds,
)

#: Deliberately awkward as well as round. 137.3 and 89.71 are the two where a
#: naive round-trip bound fails.
TEMPOS = (120.0, 124.0, 137.3, 89.71, 200.0, 40.0)
SIGNATURES = ((4, 4), (3, 4), (6, 8), (7, 8))


# --------------------------------------------------------------------------- #
# conversions
# --------------------------------------------------------------------------- #


def test_seconds_are_just_samples_over_the_rate() -> None:
    assert to_seconds(SAMPLE_RATE) == 1.0
    assert from_seconds(1.0) == SAMPLE_RATE
    assert from_seconds(to_seconds(12_345)) == 12_345


def test_bpm_counts_quarters_whatever_the_time_signature_says() -> None:
    """The convention, asserted because the alternative reading is defensible.

    At 6/8 a beat is an eighth, so it is half as long as the quarter the BPM
    counts — and a bar of six eighths is three quarters, the same length as a
    3/4 bar.
    """
    assert samples_per_beat(120.0, (4, 4)) == 24_000.0
    assert samples_per_beat(120.0, (3, 4)) == 24_000.0
    assert samples_per_beat(120.0, (6, 8)) == 12_000.0
    assert samples_per_bar(120.0, (6, 8)) == samples_per_bar(120.0, (3, 4))


def test_the_project_start_reads_as_one_one_zero() -> None:
    """04-ui-spec.md draws `1.1.000` in the toolbar."""
    assert str(to_bar_beat(0, 120.0, (4, 4))) == "1.1.000"


def test_bars_and_beats_advance_where_they_should() -> None:
    beat = int(samples_per_beat(120.0, (4, 4)))
    assert to_bar_beat(beat, 120.0, (4, 4)) == BarBeat(1, 2, 0)
    assert to_bar_beat(beat * 4, 120.0, (4, 4)) == BarBeat(2, 1, 0)
    assert to_bar_beat(beat * 3, 120.0, (3, 4)) == BarBeat(2, 1, 0)


@pytest.mark.parametrize("bpm", TEMPOS)
@pytest.mark.parametrize("signature", SIGNATURES)
def test_grid_positions_round_trip_exactly(
    bpm: float, signature: tuple[int, int]
) -> None:
    """The claim everything downstream leans on: an arrangement quantised to
    the grid stays quantised.

    Built from a musical position rather than an arbitrary sample, because
    that is what a snapped clip start is.
    """
    for bar in range(1, 400, 7):
        for beat in range(1, signature[0] + 1):
            for tick in (0, 1, 160, 240, TICKS_PER_BEAT - 1):
                position = BarBeat(bar, beat, tick)
                sample = from_bar_beat(position, bpm, signature)
                assert to_bar_beat(sample, bpm, signature) == position


@pytest.mark.parametrize("bpm", TEMPOS)
def test_an_arbitrary_sample_round_trips_within_half_a_tick_plus_half_a_sample(
    bpm: float,
) -> None:
    """Two roundings compose: to the nearest tick, then to the nearest sample.

    The acceptance originally said "half a tick", which fails at 137.3 BPM by
    0.08 of a sample — arithmetic, not a bug. See the amendment in the phase
    doc.
    """
    bound = samples_per_beat(bpm, (4, 4)) / TICKS_PER_BEAT / 2 + 0.5
    for sample in range(0, 5_000_000, 9_973):
        back = from_bar_beat(to_bar_beat(sample, bpm, (4, 4)), bpm, (4, 4))
        assert abs(back - sample) <= bound


def test_a_zero_or_negative_tempo_says_so() -> None:
    with pytest.raises(ValueError, match="bpm must be positive"):
        samples_per_beat(0.0, (4, 4))
    with pytest.raises(ValueError, match="time_signature must be positive"):
        samples_per_beat(120.0, (4, 0))


# --------------------------------------------------------------------------- #
# the grid
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("signature", SIGNATURES)
@pytest.mark.parametrize("division", list(Division))
@pytest.mark.parametrize("triplet", [False, True])
def test_every_division_lands_on_whole_ticks(
    signature: tuple[int, int], division: Division, triplet: bool
) -> None:
    """The property that made 960 the right number rather than 1000.

    A division that is silently fractional is an arrangement that will not line
    up, discovered by ear three milestones later.
    """
    ticks = TICKS_PER_BEAT * signature[1] / division.denominator
    if triplet:
        ticks = ticks * 2 / 3
    assert ticks == int(ticks), "this division is not a whole number of ticks"
    assert division_ticks(division, triplet, signature) == int(ticks)


def test_divisions_are_in_the_ratios_they_claim() -> None:
    quarter = division_ticks(Division.QUARTER, False, (4, 4))
    assert division_ticks(Division.EIGHTH, False, (4, 4)) == quarter // 2
    assert division_ticks(Division.HALF, False, (4, 4)) == quarter * 2
    assert division_ticks(Division.QUARTER, True, (4, 4)) == quarter * 2 // 3


def test_a_quarter_at_120_is_half_a_second() -> None:
    assert grid_step(Division.QUARTER, False, 120.0, (4, 4)) == 24_000.0


# --------------------------------------------------------------------------- #
# snapping
# --------------------------------------------------------------------------- #

STEP = 6_000  # a 1/16 at 120 BPM


def _snap(sample: int, edges: Sequence[int] = ()) -> int:
    """Snap on the 1/16 grid at 120 BPM, which is what STEP describes."""
    return snap(
        sample,
        bpm=120.0,
        time_signature=(4, 4),
        division=Division.SIXTEENTH,
        edges=edges,
    )


def test_snapping_off_returns_the_position_untouched() -> None:
    """What a disabled SnapSetting and a held Alt both resolve to."""
    assert snap(12_345, bpm=120.0, time_signature=(4, 4), division=None) == 12_345


def test_snapping_picks_the_nearer_grid_line() -> None:
    assert _snap(STEP // 2 - 1) == 0
    assert _snap(STEP // 2 + 1) == STEP
    assert _snap(STEP * 7 + 10) == STEP * 7


def test_a_tie_goes_to_the_later_candidate() -> None:
    """Stated so the result does not depend on a float comparison falling one
    way rather than the other, which would flicker under a still mouse."""
    assert _snap(STEP // 2) == STEP


@pytest.mark.parametrize("bpm", TEMPOS)
@pytest.mark.parametrize("division", list(Division))
def test_snapping_is_idempotent(bpm: float, division: Division) -> None:
    """A snap that drifts on repeated application moves clips nobody dragged."""
    for sample in range(0, 400_000, 3_137):
        once = snap(sample, bpm=bpm, time_signature=(4, 4), division=division)
        assert snap(once, bpm=bpm, time_signature=(4, 4), division=division) == once


def test_a_clip_edge_just_inside_a_grid_line_wins() -> None:
    """The assertion that separates "nearest of both" from "grid, then edges".

    F-17 asks for the grid *and* clip edges. An edge sitting a few samples
    inside a grid line is the case people snap to most, and it is exactly the
    case a grid-first implementation makes unreachable.
    """
    edge = STEP * 3 - 40
    assert _snap(STEP * 3 - 50, edges=[edge]) == edge
    # ...and the grid still wins when it is genuinely nearer.
    assert _snap(STEP * 3 - 5, edges=[edge]) == STEP * 3


def test_edges_beyond_the_neighbours_are_ignored() -> None:
    """The search is a bisect, so cost does not grow with the clip count."""
    edges = list(range(0, 1_000_000, 9_000))
    assert _snap(STEP * 2, edges=edges) == STEP * 2


def test_snapping_with_no_edges_matches_snapping_with_far_away_ones() -> None:
    for sample in range(0, 100_000, 1_111):
        assert _snap(sample, edges=[10**9]) == _snap(sample)


# --------------------------------------------------------------------------- #
# the per-channel override (F-18)
# --------------------------------------------------------------------------- #


def _project_with_override(override: SnapSetting | None) -> tuple[Project, Channel]:
    channel = Channel("c-00000001", "A", "#A855F7", snap_override=override)
    project = Project(
        snap=SnapSetting(enabled=True, division=Division.QUARTER), channels=[channel]
    )
    return project, channel


def test_no_override_inherits_the_project_setting() -> None:
    project, channel = _project_with_override(None)
    assert effective_snap(project, channel).division is Division.QUARTER


def test_an_override_wins_over_the_project() -> None:
    project, channel = _project_with_override(
        SnapSetting(division=Division.THIRTY_SECOND)
    )
    assert effective_snap(project, channel).division is Division.THIRTY_SECOND


def test_an_override_can_disable_snapping_entirely() -> None:
    """F-18 says "including disabling it", which is the half that gets lost."""
    project, channel = _project_with_override(SnapSetting(enabled=False))
    assert effective_snap(project, channel).enabled is False


# --------------------------------------------------------------------------- #
# D-52 — the most surprising rule in the model
# --------------------------------------------------------------------------- #


def test_changing_the_bpm_moves_the_grid_and_not_the_material() -> None:
    """D-52, asserted rather than commented.

    Clips and keyframes are stored in samples, so the tempo change slides the
    bar lines out from under an arrangement that does not move. Material lined
    up to bars at 120 is *not* lined up at 124. This is the rule most likely to
    be "fixed" by someone who thinks it is a bug, so it gets a test that says
    what it is.
    """
    media = MediaFile("m-00000001", "a.wav", "a.wav", SAMPLE_RATE, 1, 10**6)
    clips = [
        Clip("k-00000001", "m-00000001", 0, 0, 24_000),
        Clip("k-00000002", "m-00000001", 96_000, 0, 24_000),
    ]
    curve = Curve([Keyframe(0, 0.0), Keyframe(48_000, 1.0)])
    channel = Channel(
        "c-00000001", "A", "#A855F7", automation={"pos.x": curve}, clips=clips
    )
    project = Project(bpm=120.0, media_pool=[media], channels=[channel])

    before_samples = [clip.start for clip in clips] + [k.t for k in curve.keyframes]
    before_bars = [
        to_bar_beat(clip.start, project.bpm, project.time_signature) for clip in clips
    ]

    project.bpm = 124.0

    after_samples = [clip.start for clip in clips] + [k.t for k in curve.keyframes]
    after_bars = [
        to_bar_beat(clip.start, project.bpm, project.time_signature) for clip in clips
    ]

    assert after_samples == before_samples, "the material moved, and it must not"
    assert after_bars != before_bars, "the grid did not move, and it must"
    # The clip that was on bar 3 is no longer on a bar line at all.
    assert before_bars[1] == BarBeat(2, 1, 0)
    assert after_bars[1].tick != 0 or after_bars[1].beat != 1
