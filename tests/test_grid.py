"""The grid and the ruler's marks, as numbers: no window, no Qt."""

from __future__ import annotations

import itertools
import math

import pytest

from immersive.core.model import Project, SnapSetting
from immersive.core.time import (
    SAMPLE_RATE,
    BarBeat,
    Division,
    from_bar_beat,
    grid_step,
    samples_per_beat,
    snap,
)
from immersive.ui.time_axis import MAX_SCALE, MIN_SCALE
from immersive.ui.timeline.grid import (
    LABEL_SPACING,
    MIN_SPACING,
    TIME_STEPS_MS,
    Level,
    Line,
    Mark,
    Unit,
    grid_lines,
    ruler_marks,
    tempo_of,
    time_label,
)

#: 120 in 4/4; a compound time, where a beat is an eighth; and a tempo whose
#: beat is not a whole number of samples.
TEMPOS = [(120.0, (4, 4)), (120.0, (6, 8)), (97.3, (4, 4))]

#: Every zoom from the closest to the widest, a factor of two apart.
SCALES = [MIN_SCALE * 2**n for n in range(int(math.log2(MAX_SCALE)) + 1)]

DIVISIONS = [(division, triplet) for division in Division for triplet in (False, True)]


def lines(
    bpm: float,
    signature: tuple[int, int],
    scale: float,
    *,
    division: Division | None = Division.SIXTEENTH,
    triplet: bool = False,
    seconds: float = 20.0,
    start: float = 0.0,
) -> list[Line]:
    return grid_lines(
        start,
        start + seconds * SAMPLE_RATE,
        scale,
        bpm=bpm,
        time_signature=signature,
        division=division,
        triplet=triplet,
    )


def of(level: Level, drawn: list[Line]) -> list[int]:
    return [line.sample for line in drawn if line.level is level]


# --------------------------------------------------------------------------- #
# where lines go
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("bpm", "signature"), TEMPOS)
def test_bars_and_beats_fall_where_core_time_puts_them(
    bpm: float, signature: tuple[int, int]
) -> None:
    drawn = lines(bpm, signature, scale=50.0, division=None, seconds=60)
    per_bar = signature[0]
    bars = of(Level.BAR, drawn)
    beats = of(Level.BEAT, drawn)

    assert bars == [from_bar_beat(BarBeat(n, 1, 0), bpm, signature) for n in
                    range(1, len(bars) + 1)]  # fmt: skip
    expected_beats = [
        from_bar_beat(BarBeat(bar, beat, 0), bpm, signature)
        for bar in range(1, len(bars) + 1)
        for beat in range(2, per_bar + 1)
    ]
    assert beats == [b for b in expected_beats if b <= 60 * SAMPLE_RATE]


@pytest.mark.parametrize(("bpm", "signature"), TEMPOS)
@pytest.mark.parametrize(("division", "triplet"), DIVISIONS)
def test_division_lines_are_where_snapping_lands(
    bpm: float, signature: tuple[int, int], division: Division, triplet: bool
) -> None:
    """A clip snapped to a line at phase 5 must sit on the line as drawn."""
    drawn = lines(bpm, signature, MIN_SCALE * 4, division=division, triplet=triplet)
    step = grid_step(division, triplet, bpm, signature)

    for sample in of(Level.DIVISION, drawn):
        assert (
            snap(
                sample,
                bpm=bpm,
                time_signature=signature,
                division=division,
                triplet=triplet,
            )
            == sample
        )
        assert round(round(sample / step) * step) == sample


def test_a_beat_in_six_eight_is_an_eighth() -> None:
    drawn = lines(120.0, (6, 8), scale=50.0, division=None, seconds=4)

    assert of(Level.BAR, drawn)[:2] == [0, 72_000]  # six eighths at 120
    assert of(Level.BEAT, drawn)[:2] == [12_000, 24_000]


def test_lines_do_not_drift_at_a_fractional_beat() -> None:
    """Two hours in, the hundred-thousandth beat is where the arithmetic says,
    not where a hundred thousand additions of a rounded beat would put it."""
    bpm = 97.3
    beat = samples_per_beat(bpm, (4, 4))
    start = 100_000 * beat - SAMPLE_RATE

    drawn = lines(bpm, (4, 4), 50.0, division=None, seconds=2, start=start)

    assert round(100_000 * beat) in {line.sample for line in drawn}


def test_lines_are_sorted_and_unique() -> None:
    drawn = lines(97.3, (4, 4), MIN_SCALE * 8, triplet=True)
    samples = [line.sample for line in drawn]
    assert samples == sorted(set(samples))


def test_a_bar_line_is_drawn_as_a_bar_and_nothing_else() -> None:
    drawn = lines(120.0, (4, 4), 50.0)
    assert 96_000 in of(Level.BAR, drawn)
    assert 96_000 not in of(Level.BEAT, drawn) + of(Level.DIVISION, drawn)


def test_only_the_asked_span_is_drawn() -> None:
    drawn = grid_lines(
        30_000,
        90_000,
        50.0,
        bpm=120.0,
        time_signature=(4, 4),
        division=Division.SIXTEENTH,
    )
    assert drawn[0].sample >= 30_000 and drawn[-1].sample <= 90_000
    assert {line.sample for line in drawn} >= {36_000, 48_000, 72_000, 90_000}


# --------------------------------------------------------------------------- #
# level of detail
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize(("bpm", "signature"), TEMPOS)
def test_no_two_lines_crowd_at_any_zoom(
    scale: float, bpm: float, signature: tuple[int, int]
) -> None:
    for division, triplet in [*DIVISIONS, (None, False)]:
        drawn = lines(
            bpm,
            signature,
            scale,
            division=division,
            triplet=triplet,
            seconds=min(600.0, 2000 * scale / SAMPLE_RATE),
        )
        for before, after in itertools.pairwise(drawn):
            # Each line is rounded to a whole sample, so a gap may lose one.
            assert after.sample - before.sample >= MIN_SPACING * scale - 1, (
                division,
                triplet,
            )


@pytest.mark.parametrize("scale", SCALES)
def test_bars_are_always_drawn_and_thin_by_powers_of_two(scale: float) -> None:
    drawn = lines(120.0, (4, 4), scale, seconds=3000 * scale / SAMPLE_RATE)
    bars = of(Level.BAR, drawn)
    bar = 4 * samples_per_beat(120.0, (4, 4))

    assert bars, "bars are the last to go, and never go"
    gaps = {round((after - before) / bar) for before, after in itertools.pairwise(bars)}
    assert len(gaps) <= 1
    if gaps:
        (every,) = gaps
        assert every & (every - 1) == 0, f"every {every} bars is not a power of two"
        if every > 1:
            assert every * bar / scale >= MIN_SPACING
            assert every / 2 * bar / scale < MIN_SPACING, "thinned more than needed"


@pytest.mark.parametrize("scale", SCALES)
def test_beats_are_drawn_exactly_when_they_fit_and_bars_then_are_whole(
    scale: float,
) -> None:
    # At least two bars in view, however close the zoom.
    seconds = max(3000 * scale / SAMPLE_RATE, 4.0)
    drawn = lines(120.0, (4, 4), scale, division=None, seconds=seconds)
    beat_px = samples_per_beat(120.0, (4, 4)) / scale

    assert bool(of(Level.BEAT, drawn)) == (beat_px >= MIN_SPACING)
    if of(Level.BEAT, drawn):
        bars = of(Level.BAR, drawn)
        assert bars[1] - bars[0] == 96_000, "beats are drawn, so no bar is skipped"


def test_triplets_among_beats_are_left_out_before_they_crowd() -> None:
    """1/4 triplets fall a third of a beat from some beats, so they must go
    while the beats, and the triplets alone, would still fit."""
    beat = samples_per_beat(120.0, (4, 4))
    scale = beat / (MIN_SPACING * 2)  # a beat is 12 px; a third of one is 4

    drawn = lines(120.0, (4, 4), scale, division=Division.QUARTER, triplet=True)

    assert of(Level.BEAT, drawn)
    assert of(Level.DIVISION, drawn) == []


def test_no_division_lines_with_snapping_off() -> None:
    drawn = lines(120.0, (4, 4), MIN_SCALE, division=None, seconds=2)
    assert of(Level.DIVISION, drawn) == []
    assert of(Level.BEAT, drawn)


def test_the_count_is_bounded_by_pixels_not_by_length() -> None:
    """Zoomed all the way out over ten hours, the lines still fit one paint."""
    width = 2000
    drawn = lines(240.0, (4, 4), MAX_SCALE, seconds=width * MAX_SCALE / SAMPLE_RATE)
    assert len(drawn) <= width // MIN_SPACING + 1


# --------------------------------------------------------------------------- #
# the ruler
# --------------------------------------------------------------------------- #


def labels(marks: list[Mark]) -> list[str]:
    return [mark.label for mark in marks if mark.label]


def test_bars_are_labelled_from_one() -> None:
    # A bar is 120 px and a beat 30: room to label bars, not beats.
    marks = ruler_marks(
        0, 5 * 96_000, 800.0, Unit.BARS, bpm=120.0, time_signature=(4, 4)
    )

    assert labels(marks)[:3] == ["1", "2", "3"]
    assert [mark.sample for mark in marks if mark.label == "2"] == [96_000]


def test_beats_are_labelled_when_there_is_room() -> None:
    marks = ruler_marks(0, 96_000, 100.0, Unit.BARS, bpm=120.0, time_signature=(4, 4))
    assert labels(marks) == ["1", "1.2", "1.3", "1.4", "2"]


@pytest.mark.parametrize("scale", SCALES)
def test_bar_labels_never_crowd_and_thin_by_powers_of_two(scale: float) -> None:
    marks = ruler_marks(
        0,
        4000 * scale,
        scale,
        Unit.BARS,
        bpm=120.0,
        time_signature=(4, 4),
        division=Division.SIXTEENTH,
    )
    labelled = [mark.sample for mark in marks if mark.label]
    assert labelled
    for before, after in itertools.pairwise(labelled):
        assert after - before >= LABEL_SPACING * scale - 1
    numbers = [
        int(mark.label) for mark in marks if mark.label and "." not in mark.label
    ]
    steps = {after - before for before, after in itertools.pairwise(numbers)}
    assert all(step & (step - 1) == 0 for step in steps)


def test_every_grid_line_has_a_tick_and_bars_are_the_major_ones() -> None:
    kwargs = {"bpm": 120.0, "time_signature": (4, 4), "division": Division.EIGHTH}
    marks = ruler_marks(0, 192_000, 50.0, Unit.BARS, **kwargs)  # type: ignore[arg-type]
    drawn = grid_lines(0, 192_000, 50.0, **kwargs)  # type: ignore[arg-type]

    assert [mark.sample for mark in marks] == [line.sample for line in drawn]
    assert [mark.sample for mark in marks if mark.major] == of(Level.BAR, drawn)


@pytest.mark.parametrize("scale", SCALES)
def test_time_labels_take_the_smallest_round_step_with_room(scale: float) -> None:
    # At least a second in view, however close the zoom: room for two labels.
    span = max(3000 * scale, SAMPLE_RATE)
    marks = ruler_marks(0, span, scale, Unit.TIME, bpm=120.0, time_signature=(4, 4))
    labelled = [mark.sample for mark in marks if mark.label]
    assert len(labelled) >= 2
    step_ms = round((labelled[1] - labelled[0]) / SAMPLE_RATE * 1000)
    ms_per_px = scale / SAMPLE_RATE * 1000

    assert step_ms in TIME_STEPS_MS
    fitting = [s for s in TIME_STEPS_MS if s / ms_per_px >= LABEL_SPACING]
    assert step_ms == (fitting[0] if fitting else TIME_STEPS_MS[-1])


def test_time_labels_read_minutes_and_seconds() -> None:
    def at(scale: float, seconds: float) -> list[str]:
        marks = ruler_marks(
            0, seconds * SAMPLE_RATE, scale, Unit.TIME, bpm=120.0, time_signature=(4, 4)
        )
        return labels(marks)

    assert at(2400.0, 20)[:3] == ["0:00", "0:05", "0:10"]  # 20 px a second
    assert at(4800.0, 40)[:3] == ["0:00", "0:10", "0:20"]  # 10: 5 s is too close
    assert at(48.0, 1)[:3] == ["0:00.0", "0:00.1", "0:00.2"]  # 1000 px a second
    assert at(48_000.0, 400)[:3] == ["0:00", "1:00", "2:00"]  # 1 px a second
    assert time_label(3_600_000, fractional=False) == "60:00"


def test_the_time_ruler_does_not_read_the_tempo() -> None:
    """The mutation this is for: minutes and seconds worked out from bars."""
    one = ruler_marks(0, 480_000, 480.0, Unit.TIME, bpm=120.0, time_signature=(4, 4))
    other = ruler_marks(0, 480_000, 480.0, Unit.TIME, bpm=73.0, time_signature=(7, 8))
    assert one == other
    assert [m.sample for m in one if m.label == "0:02"] == [96_000]


# --------------------------------------------------------------------------- #
# what the grid is drawn from
# --------------------------------------------------------------------------- #


def test_the_grid_is_drawn_from_the_projects_tempo_and_snap() -> None:
    project = Project(
        bpm=90.0,
        time_signature=(3, 4),
        snap=SnapSetting(division=Division.EIGHTH, triplet=True),
    )

    tempo = tempo_of(project)

    assert (tempo.bpm, tempo.time_signature) == (90.0, (3, 4))
    assert (tempo.division, tempo.triplet) == (Division.EIGHTH, True)


def test_snapping_off_draws_no_division() -> None:
    project = Project(snap=SnapSetting(enabled=False, division=Division.EIGHTH))
    assert tempo_of(project).division is None
