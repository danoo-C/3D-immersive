"""The palette is well-formed and the stylesheet renders.

theme.py has no Qt dependency at import time, so this runs headless.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path

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


# --------------------------------------------------------------------------- #
# the palette table in 04 is the vocabulary
# --------------------------------------------------------------------------- #

SPEC = Path(__file__).resolve().parent.parent / "docs" / "04-ui-spec.md"

#: A token name as D-74 settled it: lowercase words, dot-separated.
TOKEN_NAME = re.compile(r"^[a-z]+(?:\.[a-z]+)*$")


def palette_table() -> dict[str, str]:
    """The Colour palette table in 04, as `{token: hex}`.

    Parsed rather than duplicated, for the reason `test_model.py` parses the
    Entities block: a copy in a test is a second home for a fact, and the two
    drift in the direction nobody is looking.
    """
    text = SPEC.read_text(encoding="utf-8")
    section = re.search(r"## Colour palette\n(.*?)\n### ", text, re.S)
    assert section, "04-ui-spec.md no longer has a Colour palette section"
    rows = re.findall(
        r"^\| `([a-z.]+)` \| `(#[0-9A-Fa-f]{6})` \|", section.group(1), re.M
    )
    return dict(rows)


def test_the_palette_table_is_well_formed() -> None:
    """Thirteen tokens, each named as D-74 says and valued as a hex."""
    palette = palette_table()

    assert len(palette) == 13, sorted(palette)
    for token in palette:
        assert TOKEN_NAME.match(token), f"{token!r} is not a token name"
    assert len(set(palette.values())) == len(palette), "two tokens share a colour"


def test_the_palette_table_holds_the_colours_the_code_holds() -> None:
    """The document and `theme.py` agree on the thirteen colours.

    Checked by value here, because D-74's rename lands in the document before
    the object that will carry the names exists. Phase 1's next step ties the
    *names* together too, and this assertion stops being the interesting one
    then — but it is what can be true today, and a value drift between the
    spec and the palette is worth catching either way.
    """
    assert set(palette_table().values()) == set(PALETTE)


def test_the_old_token_names_are_gone() -> None:
    """D-74: one vocabulary, not two.

    The failure this guards against is not a typo, it is a habit — `bg-1` was
    the name for two milestones and is what anyone who read 04 before today
    would reach for.
    """
    text = SPEC.read_text(encoding="utf-8")
    stale = re.findall(r"`(bg-[0-3]|text-(?:hi|lo|dim)|accent-(?:dim|glow))`", text)
    assert not stale, f"04-ui-spec.md still uses the old token names: {set(stale)}"


# --------------------------------------------------------------------------- #
# the Theme object
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _restore_active_theme() -> Iterator[None]:
    """No test may leave a different theme behind for the next one."""
    before = theme.active()
    yield
    theme.use(before)


def a_theme(
    name: str = "Test",
    tokens: Mapping[str, str] | None = None,
    channels: tuple[str, ...] = ("#22D3EE", "#F472B6"),
    groups: Mapping[str, Mapping[str, str]] | None = None,
) -> theme.Theme:
    """A small well-formed theme, with any part of it replaced."""
    return theme.Theme(
        name=name,
        tokens={"accent": "#A855F7", "text.primary": "#CCCCCC"}
        if tokens is None
        else tokens,
        channels=channels,
        groups={"button": {"background": "accent", "text": "text.primary"}}
        if groups is None
        else groups,
    )


def test_a_group_value_naming_a_token_resolves_to_it() -> None:
    assert a_theme().value("button", "background") == "#A855F7"
    assert a_theme().value("button", "text") == "#CCCCCC"


def test_a_group_value_that_is_a_literal_is_used_as_it_stands() -> None:
    """The escape hatch for the one thing a theme wants outside the family."""
    built = a_theme(groups={"button": {"background": "#123456"}})
    assert built.value("button", "background") == "#123456"


def test_a_group_naming_a_token_that_does_not_exist_fails_at_construction() -> None:
    """Loudly, and where the mistake is - not at paint time.

    A theme error that surfaces three hours later as a wrong-coloured button
    is the failure mode this whole milestone exists to prevent, and a
    resolver that falls back to a default when it cannot find a token is
    exactly how that happens.
    """
    with pytest.raises(theme.ThemeError) as raised:
        a_theme(groups={"button": {"background": "accent.dim"}})

    assert raised.value.problems == [
        "groups.button.background: names no token 'accent.dim'"
    ]


def test_every_problem_is_reported_not_just_the_first() -> None:
    with pytest.raises(theme.ThemeError) as raised:
        theme.Theme(
            name="",
            tokens={"accent": "tomato", "Bad Name": "#A855F7"},
            channels=("#ZZZZZZ",),
            groups={"button": {"background": "nope"}},
        )

    problems = raised.value.problems
    assert len(problems) == 5, problems
    assert any("a theme has to be called something" in p for p in problems)
    assert any("'tomato' is not a #RRGGBB colour" in p for p in problems)
    assert any("'Bad Name' is not a token name" in p for p in problems)
    assert any("channels[0]" in p for p in problems)
    assert any("names no token 'nope'" in p for p in problems)


def test_a_theme_with_no_channel_colours_is_refused() -> None:
    with pytest.raises(theme.ThemeError, match="at least one channel colour"):
        a_theme(channels=())


def test_the_reserved_channel_value_is_allowed_but_not_resolved_here() -> None:
    """`channel` means *this channel's own colour*, and this has no channel.

    Accepted at construction because it is a legal group value, and refused
    at resolution because there is no honest answer - which is better than a
    quietly wrong one. M3 draws the first widget that can ask properly.
    """
    built = a_theme(groups={"clip": {"body": theme.CHANNEL}})
    assert built.problems() == []

    with pytest.raises(theme.ThemeError, match="this channel's own colour"):
        built.value("clip", "body")


def test_asking_for_something_the_theme_does_not_have_says_so() -> None:
    with pytest.raises(theme.ThemeError, match="has no token"):
        a_theme().token("surface.panel")
    with pytest.raises(theme.ThemeError, match=r"has no button\.border"):
        a_theme().value("button", "border")


def test_a_theme_is_frozen_all_the_way_down() -> None:
    """A frozen dataclass holding a plain dict is frozen where nobody writes."""
    built = a_theme()
    with pytest.raises(FrozenInstanceError):
        built.name = "Other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        built.tokens["accent"] = "#000000"  # type: ignore[index]
    with pytest.raises(TypeError):
        built.groups["button"]["background"] = "#000000"  # type: ignore[index]


def test_channel_colour_wraps_round_the_palette() -> None:
    built = a_theme()
    assert built.channel(0) == "#22D3EE"
    assert built.channel(2) == "#22D3EE"
    assert built.channel(3) == "#F472B6"


# --------------------------------------------------------------------------- #
# the active theme
# --------------------------------------------------------------------------- #


def test_the_accessor_reads_the_active_theme_rather_than_capturing_it() -> None:
    """D-76, and the assertion the module constants could never have passed.

    This is the property the milestone's last phase is built on: a theme
    switched at runtime has to reach everything, and anything that resolved a
    colour when this module was first imported will go on showing the old one
    no matter what is switched.
    """
    assert theme.color("accent") == "#A855F7"

    theme.use(a_theme(tokens={"accent": "#00FF00", "text.primary": "#CCCCCC"}))

    assert theme.color("accent") == "#00FF00"
    assert theme.group_color("button", "background") == "#00FF00"
    assert theme.channel_color(0) == "#22D3EE"


def test_an_accessor_can_be_asked_about_a_theme_that_is_not_active() -> None:
    """So a test never has to touch the global to find out an answer."""
    other = a_theme(tokens={"accent": "#FF0000", "text.primary": "#CCCCCC"})

    assert theme.color("accent", other) == "#FF0000"
    assert theme.color("accent") == "#A855F7", "the active theme is untouched"


# --------------------------------------------------------------------------- #
# the built-in is what 04 says it is
# --------------------------------------------------------------------------- #


def test_the_builtin_tokens_are_exactly_the_palette_table() -> None:
    """Names and values both, which is what step 1's test could not check.

    Two homes for one palette is two values the first time somebody edits one
    of them, and the document is the home that gets read.
    """
    assert dict(theme.BUILTIN.tokens) == palette_table()


def test_the_builtin_surfaces_are_monotonic() -> None:
    """04: deepest to lightest, and widgets rely on the ordering."""
    surfaces = [
        theme.BUILTIN.token(name)
        for name in (
            "surface.window",
            "surface.panel",
            "surface.raised",
            "surface.hover",
        )
    ]
    levels = [_luminance(colour) for colour in surfaces]
    assert levels == sorted(levels), surfaces


def test_the_builtin_is_well_formed() -> None:
    assert theme.BUILTIN.problems() == []


def test_every_group_value_on_a_built_theme_is_resolvable() -> None:
    """Why one named mutation is unobservable, asserted rather than assumed.

    Replacing `value()`'s token lookup with a fallback to the raw string -
    `tokens.get(raw, raw)` - survives the whole suite, and it should: on a
    theme that exists, every group value is a literal, the reserved channel
    value, or a token that is there, because construction refuses anything
    else. The fallback can never fire.

    That is worth an assertion rather than a shrug, because it is exactly the
    guarantee the phase that merges a user's theme over the default has to
    keep. If a merge ever produces a `Theme` without going through validation,
    this invariant is the one it broke, and the fallback stops being
    unobservable - it starts painting token *names* as colours, which Qt
    silently drops.
    """
    for built in (theme.BUILTIN, a_theme(groups={"clip": {"body": theme.CHANNEL}})):
        for group, values in built.groups.items():
            for key, raw in values.items():
                resolvable = (
                    HEX.match(raw) or raw == theme.CHANNEL or raw in built.tokens
                )
                assert resolvable, f"{built.name}: groups.{group}.{key} is {raw!r}"
