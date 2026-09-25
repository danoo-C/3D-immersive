"""Which grid lines and ruler marks to draw, as numbers.

The view and the ruler draw what this returns and decide nothing themselves,
so everything about *where* a line goes is tested here without a window.
Qt-free, like the time axis (D-94).

**Lines are placed as `core.time` places the things they mark.** Bars and
beats with `from_bar_beat`'s expression, divisions with `snap`'s, so a clip
snapped to a line sits on the line as drawn. Each is `round(index * step)`,
never a running sum, which would drift at any tempo whose beat is not a whole
number of samples.

**Level of detail is decided in ticks, where it is exact.** Several series
drawn together can come closer than any one of them alone: triplet halves
among beats leave gaps of a third of a beat. The smallest gap in a union of
two such series is their greatest common divisor, so a series is drawn only
if that gap, at the current scale, is at least `MIN_SPACING` pixels. Bars are
always drawn and are thinned by powers of two when even they would crowd;
beats are drawn whenever they fit; the snap division is drawn whenever it
fits among what is already drawn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Final

from immersive.core.model import Project
from immersive.core.time import (
    SAMPLE_RATE,
    TICKS_PER_BEAT,
    Division,
    division_ticks,
    from_seconds,
    grid_step,
    samples_per_beat,
)

#: No two lines are drawn closer than this, in pixels.
MIN_SPACING: Final = 6

#: No two ruler labels are closer than this, in pixels - room for `128.4`.
LABEL_SPACING: Final = 60

#: Steps a minutes:seconds ruler labels by, in milliseconds: the round
#: values a person counts in.
TIME_STEPS_MS: Final = (
    100, 200, 500,
    1_000, 2_000, 5_000, 10_000, 15_000, 30_000,
    60_000, 120_000, 300_000, 600_000, 900_000, 1_800_000, 3_600_000,
)  # fmt: skip


class Level(IntEnum):
    """What a line marks. Higher is coarser, and a line is drawn as the
    coarsest thing it marks - a bar line is never also a beat line."""

    DIVISION = 0
    BEAT = 1
    BAR = 2


@dataclass(frozen=True)
class Line:
    sample: int
    level: Level


class Unit(StrEnum):
    """What the ruler counts in (F-19). The grid is always bars and beats."""

    BARS = "bars"
    TIME = "time"


@dataclass(frozen=True)
class Mark:
    """A tick on the ruler, labelled or not."""

    sample: int
    label: str
    major: bool


# --------------------------------------------------------------------------- #
# the grid
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Tempo:
    """What the grid is drawn from."""

    bpm: float
    time_signature: tuple[int, int]
    division: Division | None
    triplet: bool


def tempo_of(project: Project) -> Tempo:
    """The project's grid. A disabled snap draws no division: the grid shows
    the division a drag will snap to (04, *Timeline*), and there is none."""
    snap = project.snap
    return Tempo(
        project.bpm,
        project.time_signature,
        snap.division if snap.enabled else None,
        snap.triplet,
    )


@dataclass(frozen=True)
class _Plan:
    """Which series fit at a scale, in ticks."""

    bar_ticks: int
    bar_every: int
    beats: bool
    division_ticks: int | None


def _plan(
    scale: float,
    bpm: float,
    time_signature: tuple[int, int],
    division: Division | None,
    triplet: bool,
) -> _Plan:
    px_per_tick = samples_per_beat(bpm, time_signature) / TICKS_PER_BEAT / scale
    bar_ticks = time_signature[0] * TICKS_PER_BEAT

    bar_every = 1
    while bar_ticks * bar_every * px_per_tick < MIN_SPACING:
        bar_every *= 2

    beats = TICKS_PER_BEAT * px_per_tick >= MIN_SPACING
    finest = TICKS_PER_BEAT if beats else bar_ticks * bar_every

    fitting: int | None = None
    if division is not None:
        ticks = division_ticks(division, triplet, time_signature)
        if math.gcd(ticks, finest) * px_per_tick >= MIN_SPACING:
            fitting = ticks
    return _Plan(bar_ticks, bar_every, beats, fitting)


def grid_lines(
    first: float,
    last: float,
    scale: float,
    *,
    bpm: float,
    time_signature: tuple[int, int],
    division: Division | None,
    triplet: bool = False,
) -> list[Line]:
    """The lines between samples `first` and `last`, sorted, at `scale`.

    `division` is `None` when snapping is off, and then no division lines
    are drawn: the grid shows the division a drag will snap to (04,
    *Timeline*), and there is none.
    """
    plan = _plan(scale, bpm, time_signature, division, triplet)
    beat = samples_per_beat(bpm, time_signature)
    tick_first = math.floor(max(first, 0) / beat * TICKS_PER_BEAT)
    tick_last = math.ceil(last / beat * TICKS_PER_BEAT)

    def ticks(step: int) -> range:
        return range(-(-tick_first // step) * step, tick_last + 1, step)

    levels: dict[int, Level] = {}
    if plan.division_ticks is not None:
        for tick in ticks(plan.division_ticks):
            levels[tick] = Level.DIVISION
    if plan.beats:
        for tick in ticks(TICKS_PER_BEAT):
            levels[tick] = Level.BEAT
    for tick in ticks(plan.bar_ticks * plan.bar_every):
        levels[tick] = Level.BAR

    step = (
        grid_step(division, triplet, bpm, time_signature)
        if plan.division_ticks is not None and division is not None
        else 0.0
    )
    lines = []
    for tick, level in sorted(levels.items()):
        if level is Level.DIVISION:
            # snap's expression: whole divisions times the division - even
            # for a division line that falls on a beat, because snapping is
            # what a clip will land on.
            assert plan.division_ticks is not None
            sample = round(tick // plan.division_ticks * step)
        else:
            # from_bar_beat's: whole beats times the beat.
            sample = round(tick // TICKS_PER_BEAT * beat)
        if first <= sample <= last:
            lines.append(Line(sample, level))
    return lines


# --------------------------------------------------------------------------- #
# the ruler
# --------------------------------------------------------------------------- #


def ruler_marks(
    first: float,
    last: float,
    scale: float,
    unit: Unit,
    *,
    bpm: float,
    time_signature: tuple[int, int],
    division: Division | None = None,
    triplet: bool = False,
) -> list[Mark]:
    """The ruler's ticks between `first` and `last`, labelled where there is
    room for a label."""
    if unit is Unit.TIME:
        return _time_marks(first, last, scale)
    return _bar_marks(
        first,
        last,
        scale,
        bpm=bpm,
        time_signature=time_signature,
        division=division,
        triplet=triplet,
    )


def _bar_marks(
    first: float,
    last: float,
    scale: float,
    *,
    bpm: float,
    time_signature: tuple[int, int],
    division: Division | None,
    triplet: bool,
) -> list[Mark]:
    """A tick on every grid line, a label on bars, and on beats when there is
    room. Labelled bars thin by powers of two, as the grid's bars do."""
    beat = samples_per_beat(bpm, time_signature)
    per_bar = time_signature[0]
    bar_px = per_bar * beat / scale
    label_every = 1
    while label_every * bar_px < LABEL_SPACING:
        label_every *= 2
    beats_labelled = beat / scale >= LABEL_SPACING

    marks = []
    for line in grid_lines(
        first,
        last,
        scale,
        bpm=bpm,
        time_signature=time_signature,
        division=division,
        triplet=triplet,
    ):
        label = ""
        if line.level is not Level.DIVISION:
            index = round(line.sample / beat)
            bar, beat_in_bar = divmod(index, per_bar)
            if beat_in_bar == 0 and bar % label_every == 0:
                label = str(bar + 1)
            elif beat_in_bar and beats_labelled:
                label = f"{bar + 1}.{beat_in_bar + 1}"
        marks.append(Mark(line.sample, label, line.level is Level.BAR))
    return marks


def _time_marks(first: float, last: float, scale: float) -> list[Mark]:
    """Labels at the smallest round step that leaves room for them, and
    unlabelled ticks at the largest round step that divides it and fits."""
    ms_per_px = scale / SAMPLE_RATE * 1000
    label_ms = next(
        (step for step in TIME_STEPS_MS if step / ms_per_px >= LABEL_SPACING),
        TIME_STEPS_MS[-1],
    )
    minor_ms = next(
        (
            step
            for step in reversed(TIME_STEPS_MS)
            if step < label_ms
            and label_ms % step == 0
            and step / ms_per_px >= MIN_SPACING
        ),
        label_ms,
    )

    start = max(math.floor(first / SAMPLE_RATE * 1000 / minor_ms), 0)
    stop = math.ceil(last / SAMPLE_RATE * 1000 / minor_ms)
    marks = []
    for index in range(start, stop + 1):
        ms = index * minor_ms
        sample = from_seconds(ms / 1000)
        if not first <= sample <= last:
            continue
        labelled = ms % label_ms == 0
        text = time_label(ms, fractional=label_ms < 1000) if labelled else ""
        marks.append(Mark(sample, text, labelled))
    return marks


def time_label(ms: int, *, fractional: bool) -> str:
    """`m:ss`, with tenths when the labels are closer than a second."""
    minutes, rest = divmod(ms, 60_000)
    seconds, millis = divmod(rest, 1000)
    if fractional:
        return f"{minutes}:{seconds:02d}.{millis // 100}"
    return f"{minutes}:{seconds:02d}"
