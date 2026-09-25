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

#: Groups drawn by widgets that paint themselves, rather than through the
#: stylesheet (D-92). Every other group's keys are placeholders in `app.qss`,
#: and a test holds the sheet and those groups to each other; these are read
#: by `group_color()` calls instead, and a test holds each key to at least one
#: such call. Either way the rule is the same one: no group key that nothing
#: reads, because a role that looks themeable and is not fails silently for
#: whoever changes it.
PAINTED: Final = frozenset({"waveform", "timeline", "ruler", "clip"})


# --------------------------------------------------------------------------- #
# contrast
# --------------------------------------------------------------------------- #

#: The surfaces text is checked against. Their *ordering* - deepest first,
#: each step lighter - is a property of a theme's values and is asserted by
#: test; the rule below needs only the set.
SURFACE_TOKENS: Final = (
    "surface.window",
    "surface.panel",
    "surface.raised",
    "surface.hover",
)

#: The tokens that carry text, and so are held to 4.5:1 on every surface.
#: docs/04-ui-spec.md names two exemptions and they are expressed here by
#: absence: `text.disabled` is disabled text, and `accent` is a fill and
#: stroke colour that never carries any. `accent.text` is the text-safe
#: purple D-44 exists to provide, and is held to the rule.
#:
#: The exemptions have to live with the rule rather than with the test that
#: used to own it. A check that rediscovered them as failures would fire on
#: every load of every theme including the built-in, which is the fastest
#: way to teach somebody to ignore a report.
TEXT_TOKENS: Final = (
    "text.primary",
    "text.secondary",
    "accent.text",
    "warn",
    "error",
)

#: docs/04-ui-spec.md, *Accessibility and feel*.
TEXT_CONTRAST: Final = 4.5


def luminance(hex_colour: str) -> float:
    """WCAG relative luminance of a `#RRGGBB` colour."""
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colours."""
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def is_colour(value: str) -> bool:
    """True when `value` is a `#RRGGBB` literal.

    Public because `theme_io` has to ask the same question of every value in
    a user's file, and a second regex in a second module is a second home for
    one fact about the format.
    """
    return bool(_HEX.match(value))


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
    #: Last because the fields above have no defaults, not because it matters
    #: least. 04-ui-spec.md's file example carries an `author`, so the object
    #: has to hold one - otherwise loading the specification's own example
    #: would report a key the format documents.
    author: str = ""

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

    def contrast_problems(self) -> list[str]:
        """Every text token that falls below 4.5:1 on a surface.

        One rule, two audiences - the same split `problems()` makes, and the
        reason this is a method rather than something either caller owns. The
        built-in theme is *held* to it: `tests/test_theme.py` asserts this
        list is empty, and a built-in that failed would be a bug shipped to
        everybody. A user's theme is merely *told*: the loader reports every
        pair and loads the theme anyway, because refusing somebody's own
        theme on their own machine is not a call this application gets to
        make. docs/04-ui-spec.md argues both halves under *Contrast is
        checked, not enforced*.

        All of them rather than the first, for the reason `problems()`
        returns a list: an author fixing a palette wants to know everything
        that is wrong with it, not one item per attempt.

        A token this theme does not define is skipped rather than reported.
        Completeness is the merge's job - a loaded theme is merged over the
        built-in and therefore has every token - and a contrast check that
        also complained about absence would be answering a question nobody
        asked it.
        """
        found: list[str] = []
        for token in TEXT_TOKENS:
            if token not in self.tokens:
                continue
            for surface in SURFACE_TOKENS:
                if surface not in self.tokens:
                    continue
                ratio = contrast(self.tokens[token], self.tokens[surface])
                if ratio < TEXT_CONTRAST:
                    found.append(
                        f"{token} on {surface} is {ratio:.2f}:1, "
                        f"below {TEXT_CONTRAST}:1"
                    )
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
# the active theme
# --------------------------------------------------------------------------- #

#: One active theme for the whole application (D-76). A module-level global
#: rather than a `Theme` threaded through every widget, because there is
#: exactly one by construction — the theme picker switches the application,
#: not a panel — so the parameter would carry the same value everywhere it
#: went.
#:
#: `None` until something sets one, rather than the built-in: the default now
#: comes off disk (D-80) and reading it at import would do file I/O to answer
#: a question nobody has asked yet.
_active: Theme | None = None


def _default() -> Theme:
    """The built-in theme, read from its bundled file.

    The import is deferred because `theme_io` imports *this* module, so a
    module-level import would be a cycle (D-80). The alternative was moving
    the `.3dimtheme` format's constants in here, which would split the format
    across two modules — the thing D-77 put it in one place to avoid. A
    function-level absolute import is still greppable, which is what D-28
    cares about.
    """
    from immersive.ui.theme_io import builtin

    return builtin()


def active() -> Theme:
    """The theme the application is currently drawn in."""
    return _active if _active is not None else _default()


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
    return (theme or active()).token(name)


def group_color(group: str, key: str, theme: Theme | None = None) -> str:
    """The colour for one role of one widget, in the active theme."""
    return (theme or active()).value(group, key)


def channel_group_color(
    group: str, key: str, channel_colour: str, theme: Theme | None = None
) -> str:
    """`group_color`, for a key a theme may paint in each channel's own colour.

    The reserved `channel` value resolves to `channel_colour` - the channel's
    colour from the project - and anything else resolves as `group_color`
    would. It is what keeps 04's colour thread, a channel's header, clips and
    curves all one colour, while still letting a theme paint every clip body
    one grey if that is what it wants.
    """
    chosen = theme or active()
    if chosen.groups[group][key] == CHANNEL:
        return channel_colour
    return chosen.value(group, key)


def channel_color(index: int, theme: Theme | None = None) -> str:
    """Colour for the channel at `index`, wrapping round the palette."""
    return (theme or active()).channel(index)


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
    built = theme or active()
    # Painted groups have no placeholders - their widgets read them when they
    # paint (D-92) - and one of them may hold the reserved `channel` value,
    # which has no answer without a channel to resolve it against.
    return _template().substitute(
        {
            f"{group}.{key}".replace(".", "_"): built.value(group, key)
            for group, values in built.groups.items()
            if group not in PAINTED
            for key in values
        }
    )
