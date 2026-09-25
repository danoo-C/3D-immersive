"""What a numeric field accepts and how it shows it: no window, no Qt."""

from __future__ import annotations

import pytest

from immersive.ui.units import MINUS, parse, show


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
