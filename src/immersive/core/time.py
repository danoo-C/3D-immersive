"""Samples, seconds and bars:beats, and snapping between them.

Samples are the truth (D-11); the other two are views, computed on demand and
stored nowhere. Nothing here reads a `Project` — M4 calls these with no model
in reach, and M3 calls them on every mouse-move and should not be building one
to ask what time it is.

This module is a leaf: it imports nothing from `core`, and `model` imports
`Division` from it rather than the other way round. A grid division is a fact
about time, not about a project.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

#: D-11. One rate everywhere.
SAMPLE_RATE = 48_000

#: Ticks in one beat, where a beat is the time signature's denominator note.
#:
#: 960 rather than a rounder 1000, and the reason is triplets. F-16 requires
#: them, and a resolution that cannot express one exactly turns every triplet
#: into a rounding error that accumulates down the timeline. A triplet is
#: two-thirds of its straight division, 1000 is not divisible by 3, and 960 is
#: — so every division from 1/1 to 1/32, straight and triplet, lands on a whole
#: number of ticks at every time signature. Checked, not assumed.
TICKS_PER_BEAT = 960


class Division(StrEnum):
    """Snap grid divisions, 1/1 through 1/32 (F-16)."""

    WHOLE = "1/1"
    HALF = "1/2"
    QUARTER = "1/4"
    EIGHTH = "1/8"
    SIXTEENTH = "1/16"
    THIRTY_SECOND = "1/32"

    @property
    def denominator(self) -> int:
        """The `N` in `1/N`."""
        return int(self.value.split("/")[1])


@dataclass(frozen=True)
class BarBeat:
    """A musical position, as the ruler and the transport readout show it.

    `bar` and `beat` count from 1 because that is what a musician reads;
    `tick` counts from 0 within its beat. The start of a project is
    `1.1.000`, which is the value 04-ui-spec.md draws in the toolbar.
    """

    bar: int
    beat: int
    tick: int

    def __str__(self) -> str:
        return f"{self.bar}.{self.beat}.{self.tick:03d}"


def _check(bpm: float, time_signature: tuple[int, int]) -> None:
    if bpm <= 0:
        raise ValueError(f"bpm must be positive, got {bpm}")
    if time_signature[0] <= 0 or time_signature[1] <= 0:
        raise ValueError(f"time_signature must be positive, got {time_signature}")


def samples_per_beat(
    bpm: float, time_signature: tuple[int, int], rate: int = SAMPLE_RATE
) -> float:
    """How long one beat is, where a beat is the denominator note.

    **BPM counts quarter notes**, whatever the time signature says, which is
    what every DAW means by the number. So at 6/8 a beat is an eighth and 120
    BPM gives 12 000 samples rather than 24 000, and a bar is three quarters
    long. Written down because it is a convention rather than a derivation.
    """
    _check(bpm, time_signature)
    return rate * 60.0 / bpm * (4.0 / time_signature[1])


def samples_per_bar(
    bpm: float, time_signature: tuple[int, int], rate: int = SAMPLE_RATE
) -> float:
    return samples_per_beat(bpm, time_signature, rate) * time_signature[0]


def to_seconds(sample: int, rate: int = SAMPLE_RATE) -> float:
    return sample / rate


def from_seconds(seconds: float, rate: int = SAMPLE_RATE) -> int:
    return round(seconds * rate)


def to_bar_beat(
    sample: int, bpm: float, time_signature: tuple[int, int], rate: int = SAMPLE_RATE
) -> BarBeat:
    """Where `sample` falls, to the nearest tick."""
    per_beat = samples_per_beat(bpm, time_signature, rate)
    total = round(sample / per_beat * TICKS_PER_BEAT)
    per_bar = TICKS_PER_BEAT * time_signature[0]
    bar, remainder = divmod(total, per_bar)
    beat, tick = divmod(remainder, TICKS_PER_BEAT)
    return BarBeat(bar + 1, beat + 1, tick)


def from_bar_beat(
    position: BarBeat,
    bpm: float,
    time_signature: tuple[int, int],
    rate: int = SAMPLE_RATE,
) -> int:
    """The sample a musical position lands on.

    Exact in the direction that matters: a position built here converts back
    through `to_bar_beat` to the identical `BarBeat`, at every tempo tried, out
    to an hour of audio. Going the other way costs up to half a tick plus half
    a sample, because the two roundings compose.
    """
    beats = (position.bar - 1) * time_signature[0] + (position.beat - 1)
    total = beats * TICKS_PER_BEAT + position.tick
    return round(total / TICKS_PER_BEAT * samples_per_beat(bpm, time_signature, rate))


def division_ticks(
    division: Division, triplet: bool, time_signature: tuple[int, int]
) -> int:
    """Ticks spanned by one grid step. Always whole — see `TICKS_PER_BEAT`."""
    ticks = TICKS_PER_BEAT * time_signature[1] // division.denominator
    return ticks * 2 // 3 if triplet else ticks


def grid_step(
    division: Division,
    triplet: bool,
    bpm: float,
    time_signature: tuple[int, int],
    rate: int = SAMPLE_RATE,
) -> float:
    """Samples between two grid lines. Not rounded — the caller rounds once."""
    ticks = division_ticks(division, triplet, time_signature)
    return ticks / TICKS_PER_BEAT * samples_per_beat(bpm, time_signature, rate)


def snap(
    sample: int,
    *,
    bpm: float,
    time_signature: tuple[int, int],
    division: Division | None,
    triplet: bool = False,
    edges: Sequence[int] = (),
    rate: int = SAMPLE_RATE,
) -> int:
    """The nearest of the bracketing grid lines and the neighbouring edges.

    `division` of `None` means snapping is off and the position is returned
    untouched — which is what a disabled `SnapSetting` and a held `Alt` both
    resolve to.

    **Nearest wins outright.** F-17 asks for the grid *and* clip edges, and a
    reading where the grid is tried first, or wins ties, makes an edge sitting
    just inside a grid line unreachable — which is the case people snap to
    most. Ties go to the later candidate, stated so the result does not depend
    on which way a float comparison happens to fall.

    `edges` must be sorted; the search is a bisect over it plus two grid
    candidates, so the cost does not grow with the number of clips.
    """
    if division is None:
        return sample

    step = grid_step(division, triplet, bpm, time_signature, rate)
    lower = math.floor(sample / step)
    # Both neighbours, so a float landing a hair below an exact grid line
    # still finds it — which is what keeps snapping idempotent.
    candidates = [round(lower * step), round((lower + 1) * step)]

    if edges:
        index = bisect.bisect_left(edges, sample)
        if index > 0:
            candidates.append(edges[index - 1])
        if index < len(edges):
            candidates.append(edges[index])

    return min(candidates, key=lambda candidate: (abs(candidate - sample), -candidate))
