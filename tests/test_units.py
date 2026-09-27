"""What a numeric field accepts and how it shows it: no window, no Qt."""

from __future__ import annotations

import pytest

from immersive.core.time import SAMPLE_RATE
from immersive.ui.timeline.grid import Unit
from immersive.ui.units import MINUS, Duration, Plain, Position, parse, show


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-6", -6.0),
        ("-6dB", -6.0),
        ("-6 dB", -6.0),
        ("-6 db", -6.0),
        ("  -6 DB  ", -6.0),
        (f"{MINUS}6 dB", -6.0),
        ("+3.5", 3.5),
        ("0", 0.0),
        (".5 dB", 0.5),
    ],
)
def test_a_number_is_read_with_or_without_its_unit(text: str, expected: float) -> None:
    assert parse(text, "dB") == expected


@pytest.mark.parametrize(
    "text", ["loud", "", "   ", "dB", "-6 dBx", "6 s", "inf", "nan"]
)
def test_what_is_not_a_number_of_the_unit_is_refused(text: str) -> None:
    assert parse(text, "dB") is None


def test_a_field_without_a_unit_reads_a_bare_number() -> None:
    assert parse("120.5", "") == 120.5
    assert parse("120.5 BPM", "") is None


def test_values_are_shown_with_their_unit_and_their_sign() -> None:
    assert show(-6, "dB") == "-6.0 dB"
    assert show(3, "dB", signed=True) == "+3.0 dB"
    assert show(120, decimals=1) == "120.0"


@pytest.mark.parametrize("value", [-0.0, -0.04, 0.04])
def test_zero_is_never_shown_as_minus_zero(value: float) -> None:
    assert show(value, "dB") == "0.0 dB"
    assert show(value, "dB", signed=True) == "0.0 dB"


# --------------------------------------------------------------------------- #
# formats (D-103)
# --------------------------------------------------------------------------- #

SECOND = SAMPLE_RATE


def test_a_plain_format_is_the_number_and_its_unit() -> None:
    gain = Plain("dB", signed=True)
    assert gain.show(-6) == "-6.0 dB" and gain.parse("-6 dB") == -6.0
    assert Plain("BPM").show(120) == "120.0 BPM"


@pytest.mark.parametrize(
    ("text", "unit", "samples"),
    [
        ("1.5 s", "s", 72_000),
        ("1.5", "s", 72_000),
        ("250 ms", "s", 12_000),
        ("250ms", "s", 12_000),
        ("250 MS", "s", 12_000),
        ("250", "ms", 12_000),
        ("0.25 s", "ms", 12_000),
        ("0", "ms", 0),
    ],
)
def test_a_duration_takes_seconds_or_milliseconds(
    text: str, unit: str, samples: int
) -> None:
    assert Duration(unit).parse(text) == samples


@pytest.mark.parametrize("text", ["", "s", "ms", "long", "1.5 m", "inf s", "1.5 sec"])
def test_what_is_not_a_duration_is_refused(text: str) -> None:
    assert Duration("s").parse(text) is None


def test_durations_are_shown_in_their_own_unit() -> None:
    assert Duration("s").show(72_000) == "1.500 s"
    assert Duration("ms", decimals=0).show(12_000) == "250 ms"


class Ruler:
    """What a position format asks for, each time: a tempo and a unit."""

    def __init__(self, bpm: float = 120.0, unit: Unit = Unit.BARS) -> None:
        self.bpm = bpm
        self.signature = (4, 4)
        self.unit = unit

    def format(self) -> Position:
        return Position(lambda: (self.bpm, self.signature), lambda: self.unit)


BAR_AT_120 = 4 * SECOND // 2  # four beats of half a second
BAR_AT_90 = 4 * SECOND * 60 // 90


@pytest.mark.parametrize(
    ("text", "bpm", "samples"),
    [
        ("2.1.000", 120, BAR_AT_120),
        ("2.1.000", 90, BAR_AT_90),
        ("2", 120, BAR_AT_120),
        ("2.3", 120, BAR_AT_120 + SECOND),
        ("1.1.480", 120, SECOND // 4),
        ("1.1.000", 120, 0),
        ("0:02.5", 120, 120_000),
        ("0:02.5", 90, 120_000),
        ("1:30", 120, 90 * SECOND),
        ("1.5 s", 90, 72_000),
        ("250 ms", 90, 12_000),
    ],
)
def test_a_position_is_read_by_its_shape(text: str, bpm: float, samples: int) -> None:
    assert Ruler(bpm).format().parse(text) == samples


def test_in_minutes_and_seconds_a_bare_number_is_seconds() -> None:
    ruler = Ruler(unit=Unit.TIME)
    assert ruler.format().parse("2.5") == 120_000
    assert ruler.format().parse("2.1.000") is None, "not bars, in seconds"


@pytest.mark.parametrize(
    "text", ["", "bar", "0.1.000", "1.0.000", "-2", "1.1.1.1", "a:10", "1:-5", "1:x"]
)
def test_what_is_not_a_position_is_refused(text: str) -> None:
    assert Ruler().format().parse(text) is None


def test_a_position_is_shown_as_the_ruler_counts() -> None:
    ruler = Ruler()
    fmt = ruler.format()
    assert fmt.show(BAR_AT_120) == "2.1.000"
    ruler.unit = Unit.TIME
    assert fmt.show(120_000) == "0:02.500"
    assert fmt.show(90 * SECOND + 1) == "1:30.000"


def test_a_position_reads_the_tempo_each_time_it_is_shown() -> None:
    """Never kept: a start shown after a tempo change is in the new bars."""
    ruler = Ruler(bpm=120)
    fmt = ruler.format()
    assert fmt.show(BAR_AT_90) == "2.2.320"
    ruler.bpm = 90
    assert fmt.show(BAR_AT_90) == "2.1.000"
    assert fmt.parse("2.1.000") == BAR_AT_90


@pytest.mark.parametrize("bpm", [90.0, 120.0, 137.3])
@pytest.mark.parametrize("unit", list(Unit))
def test_a_position_reads_back_what_it_shows(bpm: float, unit: Unit) -> None:
    fmt = Ruler(bpm, unit).format()
    for samples in (0, BAR_AT_120, 7 * SECOND + 480, 3_600 * SECOND):
        again = fmt.parse(fmt.show(samples))
        assert again is not None
        # To the text's own resolution: a tick in bars, a millisecond in time.
        assert abs(again - samples) <= SECOND // 1000 + 1 or unit is Unit.BARS
        assert fmt.show(again) == fmt.show(samples)
