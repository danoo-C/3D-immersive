"""Numbers with units, as a person types them and as a field shows them.

Qt-free, like the time axis and the grid, so what a field will accept is
tested without a window. `NumericField` is the widget; this is its grammar.
"""

from __future__ import annotations

import math

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
