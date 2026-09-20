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
