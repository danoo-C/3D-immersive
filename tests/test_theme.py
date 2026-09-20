"""The palette is well-formed and the stylesheet renders.

theme.py has no Qt dependency at import time, so this runs headless.
"""

from __future__ import annotations

import re

import pytest

from immersive.ui import theme

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

PALETTE = (
    theme.BG_0,
    theme.BG_1,
    theme.BG_2,
    theme.BG_3,
    theme.BORDER,
    theme.TEXT_HI,
    theme.TEXT_LO,
    theme.TEXT_DIM,
    theme.ACCENT,
    theme.ACCENT_DIM,
    theme.ACCENT_GLOW,
    theme.WARN,
    theme.ERROR,
)


@pytest.mark.parametrize("value", PALETTE)
def test_palette_entries_are_hex(value: str) -> None:
    assert HEX.match(value), value


def test_channel_colors_are_distinct_and_hex() -> None:
    assert len(theme.CHANNEL_COLORS) == 8
    assert len(set(theme.CHANNEL_COLORS)) == len(theme.CHANNEL_COLORS)
    for value in theme.CHANNEL_COLORS:
        assert HEX.match(value), value


def test_channel_color_wraps() -> None:
    n = len(theme.CHANNEL_COLORS)
    assert theme.channel_color(0) == theme.CHANNEL_COLORS[0]
    assert theme.channel_color(n) == theme.CHANNEL_COLORS[0]
    assert theme.channel_color(n + 3) == theme.CHANNEL_COLORS[3]


def test_stylesheet_substitutes_every_placeholder() -> None:
    qss = theme.stylesheet()
    assert "{" not in qss.replace("{{", "").replace("}}", "") or "QWidget" in qss
    # No unsubstituted format fields should survive.
    assert not re.search(r"\{[a-z_]+\}", qss)
    assert theme.ACCENT in qss
    assert theme.BG_0 in qss


def test_stylesheet_parses(capfd: pytest.CaptureFixture[str]) -> None:
    """Qt must accept the QSS, not merely receive it.

    The substitution test above passes on a stylesheet Qt cannot parse — one
    stray `*/` is enough — and Qt's only complaint is "Could not parse
    application stylesheet", after which the entire application silently
    renders unstyled. `capfd`, not `capsys`: that warning comes out of Qt's
    C++ message handler at the file-descriptor level and never passes through
    Python's sys.stderr, so capsys sees nothing and the test would pass on a
    broken sheet — which is the exact failure it exists to catch.
    """
    from PySide6.QtWidgets import QToolButton, QWidget

    from immersive.app import build_application

    app = build_application([])
    app.setStyleSheet(theme.stylesheet())

    # Qt parses the sheet when it first polishes a widget against it, not when
    # it is set, so asserting straight after setStyleSheet catches nothing.
    capfd.readouterr()
    probe = QWidget()
    QToolButton(probe)
    probe.show()
    app.processEvents()

    assert "Could not parse" not in capfd.readouterr().err
    assert app.styleSheet() == theme.stylesheet()


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colours."""
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


SURFACES = (theme.BG_0, theme.BG_1, theme.BG_2, theme.BG_3)

# 04-ui-spec.md promises 4.5:1 for text on every surface. TEXT_DIM (disabled)
# and ACCENT (a fill and stroke colour, never text) are the two documented
# exemptions; ACCENT_GLOW is the text-safe purple and is held to the rule.
TEXT_TOKENS = (theme.TEXT_HI, theme.TEXT_LO, theme.ACCENT_GLOW, theme.WARN, theme.ERROR)


@pytest.mark.parametrize("colour", TEXT_TOKENS)
@pytest.mark.parametrize("surface", SURFACES)
def test_text_contrast_meets_the_spec(colour: str, surface: str) -> None:
    assert contrast(colour, surface) >= 4.5, f"{colour} on {surface}"


@pytest.mark.parametrize("colour", theme.CHANNEL_COLORS)
def test_channel_colours_are_legible_on_panels(colour: str) -> None:
    """04-ui-spec.md: channel colours must stay legible on bg-1."""
    assert contrast(colour, theme.BG_1) >= 3.0, colour


def test_accent_clears_the_ui_component_threshold() -> None:
    """ACCENT is not text, but a playhead nobody can see is still a bug."""
    for surface in SURFACES:
        assert contrast(theme.ACCENT, surface) >= 3.0, surface


def test_surfaces_are_monotonic() -> None:
    """bg-0 is deepest and each step is lighter; widgets rely on the ordering."""
    levels = [_luminance(s) for s in SURFACES]
    assert levels == sorted(levels), levels
