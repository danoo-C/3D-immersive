"""Numbers with units, as a person types them and as a field shows them.

Qt-free, like the time axis and the grid, so what a field will accept is
tested without a window. `NumericField` is the widget; this is its grammar.

A **format** is one field's whole grammar: a gain in decibels, a duration
in seconds or milliseconds, a position on the timeline as the ruler counts
it (D-103). `parse` and `show` are the plain number-and-unit case every
format but the timeline's is built on.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from immersive.core.time import SAMPLE_RATE, BarBeat, from_bar_beat, to_bar_beat
from immersive.ui.timeline.grid import Unit

#: The typographic minus, which anything that typesets its numbers - a
#: manual, a web page, a spreadsheet - hands over when one is pasted.
MINUS = "\N{MINUS SIGN}"


def parse(text: str, unit: str = "") -> float | None:
    """`text` as a number of `unit`s, or `None` when it is not one.

    The unit may be left off, and is matched ignoring case and the space
    before it, so `-6`, `-6dB` and `-6 db` are all minus six decibels.
    Infinity and not-a-number are not values any field here can hold.
    """
    cleaned = text.strip().replace(MINUS, "-")
    if unit and cleaned.lower().endswith(unit.lower()):
        cleaned = cleaned[: -len(unit)].rstrip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def show(
    value: float, unit: str = "", *, decimals: int = 1, signed: bool = False
) -> str:
    """`value` as a field shows it: `-6.0 dB`, or `+3.0 dB` when `signed`.

    Never `-0.0`: a value that rounds to zero is shown as zero, whichever
    side of it the arithmetic happened to land.
    """
    text = f"{value:+.{decimals}f}" if signed else f"{value:.{decimals}f}"
    if float(text) == 0:
        text = f"{0:.{decimals}f}"
    return f"{text} {unit}" if unit else text


# --------------------------------------------------------------------------- #
# formats: what a field shows, and what it takes
# --------------------------------------------------------------------------- #


class Format(Protocol):
    """How a field shows its value and reads what is typed into it.

    The value is whatever the field holds - decibels for a gain, samples for
    a start or a length - and the format is the only thing that knows how a
    person writes it.
    """

    def show(self, value: float) -> str: ...

    def parse(self, text: str) -> float | None: ...


@dataclass(frozen=True)
class Plain:
    """A number and its unit: `-6.0 dB`, `120.0 BPM`."""

    unit: str = ""
    decimals: int = 1
    signed: bool = False

    def show(self, value: float) -> str:
        return show(value, self.unit, decimals=self.decimals, signed=self.signed)

    def parse(self, text: str) -> float | None:
        return parse(text, self.unit)


#: Samples in one of each unit a duration may be typed in.
_SAMPLES_IN = {"s": SAMPLE_RATE, "ms": SAMPLE_RATE / 1000}


@dataclass(frozen=True)
class Duration:
    """A length of time held in samples, shown in seconds or milliseconds
    and typed in either (D-103): `1.500 s`, `250 ms`."""

    unit: str = "s"
    decimals: int = 3

    def show(self, value: float) -> str:
        return show(value / _SAMPLES_IN[self.unit], self.unit, decimals=self.decimals)

    def parse(self, text: str) -> float | None:
        return _seconds_or_millis(text, self.unit)


@dataclass(frozen=True)
class Position:
    """A point on the timeline held in samples, shown as the ruler counts -
    `2.1.000` or `0:02.000` - and typed either way, or in `s` or `ms`
    (D-103).

    The tempo and the ruler's unit are asked for each time, never kept: a
    start shown after a tempo change is in the new tempo's bars.

    What is typed is read by its shape: `2.1.000`, `2.1` or `2` in the
    ruler's bars; anything with a colon as minutes and seconds; `s` or `ms`
    as a duration from the start. A bare number in minutes:seconds is
    seconds.
    """

    tempo: Callable[[], tuple[float, tuple[int, int]]]
    unit: Callable[[], Unit]

    def show(self, value: float) -> str:
        sample = max(round(value), 0)
        if self.unit() is Unit.BARS:
            bpm, signature = self.tempo()
            return str(to_bar_beat(sample, bpm, signature))
        return clock(sample)

    def parse(self, text: str) -> float | None:
        cleaned = text.strip().replace(MINUS, "-")
        if ":" in cleaned:
            minutes, _, seconds = cleaned.partition(":")
            if not minutes.strip().isdigit():
                return None
            rest = _number(seconds)
            if rest is None or rest < 0:
                return None
            return round((int(minutes) * 60 + rest) * SAMPLE_RATE)
        if cleaned.lower().endswith("s") or self.unit() is Unit.TIME:
            return _seconds_or_millis(cleaned, "s")
        parts = cleaned.split(".")
        if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
            return None
        # What is left off is the start of what was given: `2` is 2.1.000.
        bar, beat, tick = [int(part) for part in parts] + [1, 0][len(parts) - 1 :]
        if bar < 1 or beat < 1:
            return None
        bpm, signature = self.tempo()
        return from_bar_beat(BarBeat(bar, beat, tick), bpm, signature)


def clock(sample: int) -> str:
    """`m:ss.mmm`: minutes, seconds and milliseconds."""
    millis = round(sample * 1000 / SAMPLE_RATE)
    minutes, rest = divmod(millis, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def _number(text: str) -> float | None:
    try:
        value = float(text.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _seconds_or_millis(text: str, default: str) -> float | None:
    """`text` as samples: a number of `s` or `ms`, or of `default` when it
    names neither. `ms` is looked for first, since it ends in `s`."""
    cleaned = text.strip().replace(MINUS, "-")
    unit = default
    for suffix in ("ms", "s"):
        if cleaned.lower().endswith(suffix):
            cleaned, unit = cleaned[: -len(suffix)], suffix
            break
    number = _number(cleaned)
    return None if number is None else round(number * _SAMPLES_IN[unit])
