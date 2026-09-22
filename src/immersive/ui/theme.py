"""Palette and stylesheet.

The single source of colour for the whole application. Every colour here comes
from the *Colour palette* and *Theming* sections of docs/04-ui-spec.md, and no
widget anywhere names a hex (F-44).

**Two layers, tokens and groups** (D-46). A *token* is a named colour -
`surface.panel`, `accent.text` - and there are thirteen of them. A *group* is a
per-widget role - what a button's background is, what a splitter handle turns
when hovered - and its value is either a token name or a literal `#RRGGBB`.
Change eight tokens and the whole application is coherently retinted, because
everything else refers to them by name; reach for a literal when a theme
wants one thing to break the family.

**This module is strict, and a theme file will not be.** A `Theme` validates
at construction and raises, because the built-in theme is *code* and a group
of it naming a token that does not exist is a bug that must not ship. A
user's `.3dimtheme` is *input*, and a typo in a cosmetic file must not stand
between somebody and their project - so the phase that loads one drops what
it cannot use, reports it, and hands this module something already known to
be well-formed. One rule, two audiences; 04-ui-spec.md says the same under
*When a theme is wrong*.

No Qt import at module level, so the palette and the stylesheet are testable
headless.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from string import Template
from types import MappingProxyType
from typing import Final

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

#: A token or group name as D-74 settled it: lowercase words, dot-separated.
#: The dotted form is the same grammar a `.3dimtheme` uses for group keys, so
#: there is one spelling to learn rather than two.
_NAME = re.compile(r"^[a-z]+(?:\.[a-z]+)*$")

#: The one group value that is neither a token name nor a literal colour: it
#: means *this channel's own colour*, resolved per channel at paint time. It
#: is what keeps 04-ui-spec.md's colour thread - a channel's header, clips,
#: spatial icon and curves all one colour - intact under any theme. Nothing
#: resolves it yet; M3 draws the first widget that needs it.
CHANNEL: Final = "channel"


class ThemeError(Exception):
    """A theme that cannot be used, and every reason it cannot.

    Raised where a theme is *constructed*, never where a colour is read: a
    wrong-coloured widget discovered three hours into a session is the failure
    this whole milestone exists to prevent, and the only way to prevent it is
    to refuse the theme before anything paints.

    Carries plain strings rather than a structured record. Each one names its
    own location inline, which is enough for a developer reading a traceback,
    and the milestone's later phase - which has to show a user's theme
    problems in the notice centre - is the one that will know what structure
    that surface wants.
    """

    def __init__(self, summary: str, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        detail = "\n".join(f"  {problem}" for problem in self.problems)
        super().__init__(f"{summary}\n{detail}" if detail else summary)


@dataclass(frozen=True)
class Theme:
    """A named palette: thirteen tokens, a channel list, and the groups.

    Frozen, and frozen all the way down - the mappings are wrapped in
    `MappingProxyType` at construction, because a frozen dataclass holding a
    plain `dict` is only frozen in the places nobody was going to write to
    anyway.

    The channel list is a third top-level thing rather than a token (D-75). A
    token is one colour a group value may name; the channel palette is an
    ordered sequence indexed by position, and `"background": "channels"` names
    no colour at all.
    """

    name: str
    tokens: Mapping[str, str]
    channels: tuple[str, ...]
    groups: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        problems = self.problems()
        if problems:
            raise ThemeError(f"{self.name!r} is not a usable theme", problems)
        object.__setattr__(self, "tokens", MappingProxyType(dict(self.tokens)))
        object.__setattr__(
            self,
            "groups",
            MappingProxyType(
                {
                    name: MappingProxyType(dict(values))
                    for name, values in self.groups.items()
                }
            ),
        )

    # ----------------------------------------------------------- validation

    def problems(self) -> list[str]:
        """Every way this theme is not well-formed. Empty when it is.

        All of them rather than the first, for the reason `model.validate()`
        returns a list: somebody fixing a theme wants to know everything that
        is wrong with it, not to find out one item per attempt.
        """
        found: list[str] = []

        if not self.name:
            found.append("name: a theme has to be called something")

        for token, value in self.tokens.items():
            if not _NAME.match(token):
                found.append(f"tokens.{token}: {token!r} is not a token name")
            if not _HEX.match(value):
                found.append(f"tokens.{token}: {value!r} is not a #RRGGBB colour")

        if not self.channels:
            found.append("channels: a theme needs at least one channel colour")
        for index, value in enumerate(self.channels):
            if not _HEX.match(value):
                found.append(f"channels[{index}]: {value!r} is not a #RRGGBB colour")

        for group, values in self.groups.items():
            if not _NAME.match(group):
                found.append(f"groups.{group}: {group!r} is not a group name")
            for key, raw in values.items():
                where = f"groups.{group}.{key}"
                if not _NAME.match(key):
                    found.append(f"{where}: {key!r} is not a group key")
                if raw == CHANNEL or _HEX.match(raw):
                    continue
                if raw not in self.tokens:
                    found.append(f"{where}: names no token {raw!r}")
        return found

    # ----------------------------------------------------------- resolution

    def token(self, name: str) -> str:
        """The colour `name` stands for."""
        try:
            return self.tokens[name]
        except KeyError:
            raise ThemeError(
                f"{self.name!r} has no token {name!r}",
                [f"tokens: {name!r} is not one of {', '.join(sorted(self.tokens))}"],
            ) from None

    def value(self, group: str, key: str) -> str:
        """The colour a widget should paint `key` of `group` in.

        A token name resolves; a literal `#RRGGBB` is used as it stands. The
        reserved `channel` value does not resolve here - it has no answer
        without knowing *which* channel - and the caller that has one asks
        `channel()` instead.
        """
        try:
            raw = self.groups[group][key]
        except KeyError:
            raise ThemeError(
                f"{self.name!r} has no {group}.{key}",
                [f"groups.{group}.{key}: not defined"],
            ) from None
        if raw == CHANNEL:
            raise ThemeError(
                f"{group}.{key} is a channel colour",
                [
                    f"groups.{group}.{key}: {CHANNEL!r} means this channel's own "
                    f"colour and has to be resolved against one"
                ],
            )
        return raw if _HEX.match(raw) else self.tokens[raw]

    def channel(self, index: int) -> str:
        """Colour for the channel at `index`, wrapping round the palette."""
        return self.channels[index % len(self.channels)]


# --------------------------------------------------------------------------- #
# the built-in theme
# --------------------------------------------------------------------------- #

#: The default, and — from the phase that bundles it as a file — the thing
#: every user theme is merged over (D-45). Every colour is the one the
#: *Colour palette* table in docs/04-ui-spec.md gives, and a test parses that
#: table and asserts so, because a palette with two homes has two values the
#: first time somebody edits one of them.
BUILTIN: Final = Theme(
    name="VS Code Dark",
    tokens={
        # Surfaces are VS Code's dark greys (D-44), and monotonic:
        # surface.window is deepest and each step is lighter. Widgets rely on
        # that ordering rather than on the values, because a theme may
        # replace them.
        "surface.window": "#181818",
        "surface.panel": "#1F1F1F",
        "surface.raised": "#252526",
        "surface.hover": "#2D2D2D",
        "border": "#3C3C3C",
        "text.primary": "#CCCCCC",
        "text.secondary": "#9D9D9D",
        # Disabled text, and the one text colour exempt from the 4.5:1 rule.
        "text.disabled": "#6E6E6E",
        # The accent stays purple against the neutral greys. `accent` is a
        # fill and stroke colour — playhead, focus ring, active toggle — and
        # is 4.17:1 on surface.panel, which clears the 3:1 WCAG asks of a UI
        # component but not the 4.5:1 04-ui-spec.md promises text. Purple
        # that carries text uses accent.text.
        "accent": "#A855F7",
        "accent.pressed": "#7E3FF2",
        "accent.text": "#C77DFF",
        # Nothing styles these yet: clipping and missing media belong to
        # widgets M2 and M3 build, and load failures to the notice centre
        # this milestone's last phase builds. They are in the vocabulary
        # because a token is a colour a theme may set, not a colour something
        # currently paints.
        "warn": "#F59E0B",
        "error": "#F88A8A",
    },
    #: Assigned round-robin as channels are created; user-overridable. Chosen
    #: to stay legible on surface.panel and distinguishable from each other
    #: and from accent.
    channels=(
        "#A855F7",  # purple
        "#22D3EE",  # cyan
        "#F59E0B",  # amber
        "#34D399",  # emerald
        "#F472B6",  # pink
        "#60A5FA",  # blue
        "#FB923C",  # orange
        "#A3E635",  # lime
    ),
    #: Per-widget roles (D-46). One group per widget the application draws
    #: today, named from the ownership table in the *Theming* section of
    #: docs/04-ui-spec.md rather than from the stylesheet's selectors — a key
    #: called `toolbutton_pressed_background` would be a QSS selector with an
    #: underscore in it, not a role anybody would think to theme.
    #:
    #: Every milestone from here adds its own groups as it builds the widgets
    #: that need them, and adds them to `04` at the same time. That obligation
    #: is the whole reason this system is built third rather than last.
    groups={
        "window": {"background": "surface.window"},
        "panel": {"background": "surface.panel", "text": "text.primary"},
        "menu": {
            "bar.background": "surface.raised",
            "bar.border": "border",
            "bar.selected.background": "surface.hover",
            "background": "surface.raised",
            "border": "border",
            "selected.background": "accent.pressed",
            "selected.text": "text.primary",
            "disabled.text": "text.disabled",
            "separator": "border",
        },
        "toolbar": {
            "background": "surface.raised",
            "border": "border",
            "separator": "border",
        },
        "button": {
            "background": "surface.hover",
            "border": "border",
            "text": "text.primary",
            "hover.border": "accent.text",
            "pressed.background": "accent.pressed",
            "checked.background": "accent.pressed",
            "checked.border": "accent",
            "disabled.text": "text.disabled",
            "disabled.border": "surface.hover",
        },
        "tab": {
            "pane.background": "surface.panel",
            "bar.background": "surface.window",
            "background": "surface.window",
            "text": "text.secondary",
            "hover.background": "surface.raised",
            "hover.text": "text.primary",
            "selected.background": "surface.panel",
            "selected.text": "text.primary",
            "selected.marker": "accent",
        },
        # The focus ring is its own group rather than a key on each widget:
        # 04-ui-spec.md asks for one indicator, consistent across the
        # application and visible — "no information by colour alone" cuts both
        # ways, and a focus indicator nobody can see fails keyboard users
        # first. One group is how it stays one colour.
        "focus": {"ring": "accent", "menu.background": "surface.hover"},
        "splitter": {"handle": "border", "hover.handle": "accent"},
        "statusbar": {
            "background": "surface.raised",
            "border": "border",
            "text": "text.secondary",
        },
        "scrollbar": {
            "background": "surface.panel",
            "handle": "surface.hover",
            "hover.handle": "accent.pressed",
        },
        "tooltip": {
            "background": "surface.raised",
            "text": "text.primary",
            "border": "accent.pressed",
        },
    },
)


# --------------------------------------------------------------------------- #
# the active theme
# --------------------------------------------------------------------------- #

#: One active theme for the whole application (D-76). A module-level global
#: rather than a `Theme` threaded through every widget, because there is
#: exactly one by construction — the theme picker switches the application,
#: not a panel — so the parameter would carry the same value everywhere it
#: went.
_active: Theme = BUILTIN


def active() -> Theme:
    """The theme the application is currently drawn in."""
    return _active


def use(theme: Theme) -> None:
    """Make `theme` the active one.

    Repainting is the caller's: the stylesheet has to be rebuilt and reapplied
    and anything that baked a colour into itself has to be rebuilt too. The
    phase that adds a theme picker owns that; this is the half of it that
    belongs to the palette.
    """
    global _active
    _active = theme


def color(name: str, theme: Theme | None = None) -> str:
    """The colour token `name` stands for, in the active theme.

    **Reads, never captures** (D-76). Every caller of this resolves the colour
    at the moment it paints, which is what lets a theme change take effect
    without a restart. A module constant, or a default argument holding a
    colour, would be resolved once when this module was first imported and
    would quietly go on showing the old theme.

    `theme` is here so a test can ask a specific one without touching the
    global.
    """
    return (theme or _active).token(name)


def group_color(group: str, key: str, theme: Theme | None = None) -> str:
    """The colour for one role of one widget, in the active theme."""
    return (theme or _active).value(group, key)


def channel_color(index: int, theme: Theme | None = None) -> str:
    """Colour for the channel at `index`, wrapping round the palette."""
    return (theme or _active).channel(index)


# --------------------------------------------------------------------------- #
# transitional — removed later in this phase
# --------------------------------------------------------------------------- #

# The stylesheet below and eleven widget call sites still read these. The step
# that rewires the sheet onto groups and the step that moves the widgets onto
# `color()` delete them; they exist for exactly as long as it takes to do that
# without a commit in which the application does not start.
BG_0: Final = BUILTIN.tokens["surface.window"]
BG_1: Final = BUILTIN.tokens["surface.panel"]
BG_2: Final = BUILTIN.tokens["surface.raised"]
BG_3: Final = BUILTIN.tokens["surface.hover"]
BORDER: Final = BUILTIN.tokens["border"]
TEXT_HI: Final = BUILTIN.tokens["text.primary"]
TEXT_LO: Final = BUILTIN.tokens["text.secondary"]
TEXT_DIM: Final = BUILTIN.tokens["text.disabled"]
ACCENT: Final = BUILTIN.tokens["accent"]
ACCENT_DIM: Final = BUILTIN.tokens["accent.pressed"]
ACCENT_GLOW: Final = BUILTIN.tokens["accent.text"]
WARN: Final = BUILTIN.tokens["warn"]
ERROR: Final = BUILTIN.tokens["error"]
CHANNEL_COLORS: Final[tuple[str, ...]] = BUILTIN.channels


# --------------------------------------------------------------------------- #
# stylesheet
# --------------------------------------------------------------------------- #

#: The sheet lives beside the icons and is read through importlib.resources,
#: never by walking up from __file__ (D-30).
_QSS_PACKAGE: Final = "immersive.assets"
_QSS_FILE: Final = "app.qss"


@cache
def _template() -> Template:
    """The stylesheet template, read once per process.

    `string.Template` rather than `str.format`, so the file can hold single
    braces and be a stylesheet an editor highlights and a person can read.
    `str.format` would need every `{` in it doubled, which would make it
    neither.
    """
    text = resources.files(_QSS_PACKAGE).joinpath(_QSS_FILE).read_text("utf-8")
    return Template(text)


def stylesheet(theme: Theme | None = None) -> str:
    """The application-wide QSS, with a theme's groups substituted in.

    Every `$name` in the sheet is one group key with its dots turned into
    underscores - `$button_hover_border` is the `hover.border` key of the
    `button` group - so the stylesheet names roles and never colours, which
    is F-44. A `$name` with no group key behind it raises here rather than
    leaving a widget quietly wearing the colour it had.

    Takes a theme so the phase that adds a picker can build a sheet for one
    without making it active first. Defaults to the active theme, which is
    what `app.py` wants.
    """
    built = theme or _active
    return _template().substitute(
        {
            f"{group}.{key}".replace(".", "_"): built.value(group, key)
            for group, values in built.groups.items()
            for key in values
        }
    )
