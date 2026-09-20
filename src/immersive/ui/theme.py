"""Palette and stylesheet.

The single source of colour for the whole application. Every hex here comes
from docs/04-ui-spec.md; change it there and here together, never in a widget.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #

BG_0: Final = "#0E0B14"  # application background, deepest
BG_1: Final = "#16121F"  # panel surfaces
BG_2: Final = "#1E1929"  # headers, raised elements
BG_3: Final = "#2A2338"  # hover, selected row
BORDER: Final = "#332B44"  # 1px separators, splitter handles

TEXT_HI: Final = "#E8E4F0"  # primary text
TEXT_LO: Final = "#9A93AC"  # labels, secondary text
TEXT_DIM: Final = "#635C75"  # disabled

ACCENT: Final = "#A855F7"  # playhead, focus, active toggle
ACCENT_DIM: Final = "#7E3FF2"  # pressed
ACCENT_GLOW: Final = "#C77DFF"  # hover, keyframe highlight

WARN: Final = "#F59E0B"  # clipping, missing media
ERROR: Final = "#EF4444"  # xruns, load failures

#: Assigned round-robin as channels are created; user-overridable. Chosen to
#: stay legible on BG_1 and distinguishable from each other and from ACCENT.
CHANNEL_COLORS: Final[tuple[str, ...]] = (
    "#A855F7",  # purple
    "#22D3EE",  # cyan
    "#F59E0B",  # amber
    "#34D399",  # emerald
    "#F472B6",  # pink
    "#60A5FA",  # blue
    "#FB923C",  # orange
    "#A3E635",  # lime
)


def channel_color(index: int) -> str:
    """Colour for the channel at `index`, wrapping round the palette."""
    return CHANNEL_COLORS[index % len(CHANNEL_COLORS)]


# --------------------------------------------------------------------------- #
# stylesheet
# --------------------------------------------------------------------------- #

_QSS = """
QWidget {{
    background-color: {bg_1};
    color: {text_hi};
    font-size: 13px;
}}

QMainWindow, QMainWindow > QWidget {{ background-color: {bg_0}; }}

QMenuBar {{
    background-color: {bg_2};
    border-bottom: 1px solid {border};
    padding: 2px 4px;
}}
QMenuBar::item {{ padding: 5px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: {bg_3}; }}

QMenu {{
    background-color: {bg_2};
    border: 1px solid {border};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 24px 6px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {accent_dim}; color: {text_hi}; }}
QMenu::item:disabled {{ color: {text_dim}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}

QToolBar {{
    background-color: {bg_2};
    border-bottom: 1px solid {border};
    padding: 4px 6px;
    spacing: 4px;
}}
QToolBar::separator {{ width: 1px; background: {border}; margin: 4px 6px; }}

QToolButton, QPushButton {{
    background-color: {bg_3};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 5px 10px;
    color: {text_hi};
}}
QToolButton:hover, QPushButton:hover {{ border-color: {accent_glow}; }}
QToolButton:pressed, QPushButton:pressed {{ background-color: {accent_dim}; }}
QToolButton:checked {{
    background-color: {accent_dim};
    border-color: {accent};
}}
QToolButton:disabled, QPushButton:disabled {{
    color: {text_dim};
    border-color: {bg_3};
}}

QSplitter::handle {{ background-color: {border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background-color: {accent}; }}

QStatusBar {{
    background-color: {bg_2};
    border-top: 1px solid {border};
    color: {text_lo};
}}
QStatusBar::item {{ border: none; }}

QLabel {{ background: transparent; }}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: {bg_1};
    border: none;
}}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle {{ background: {bg_3}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:hover {{ background: {accent_dim}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QToolTip {{
    background-color: {bg_2};
    color: {text_hi};
    border: 1px solid {accent_dim};
    padding: 4px 6px;
}}
"""


def stylesheet() -> str:
    """The application-wide QSS, with the palette substituted in."""
    return _QSS.format(
        bg_0=BG_0,
        bg_1=BG_1,
        bg_2=BG_2,
        bg_3=BG_3,
        border=BORDER,
        text_hi=TEXT_HI,
        text_lo=TEXT_LO,
        text_dim=TEXT_DIM,
        accent=ACCENT,
        accent_dim=ACCENT_DIM,
        accent_glow=ACCENT_GLOW,
    )
