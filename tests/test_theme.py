"""The palette is well-formed and the stylesheet renders.

theme.py has no Qt dependency at import time, so this runs headless.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from importlib import resources
from pathlib import Path

import pytest

from immersive.ui import theme

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

PALETTE = tuple(theme.BUILTIN.tokens.values())

#: The rule moved into the package in M9 phase 2, exemptions and all: the
#: theme loader has to apply it to a user's file, and a rule implemented in a
#: test suite cannot be applied to anything. Aliased so the tests below read
#: as they always did.
SURFACE_TOKENS = theme.SURFACE_TOKENS
TEXT_TOKENS = theme.TEXT_TOKENS


@pytest.mark.parametrize("value", PALETTE)
def test_palette_entries_are_hex(value: str) -> None:
    assert HEX.match(value), value


def test_channel_colors_are_distinct_and_hex() -> None:
    channels = theme.BUILTIN.channels
    assert len(channels) == 8
    assert len(set(channels)) == len(channels)
    for value in channels:
        assert HEX.match(value), value


def test_channel_color_wraps() -> None:
    """`channel_color(i)` keeps the signature and behaviour it always had."""
    channels = theme.BUILTIN.channels
    n = len(channels)
    assert theme.channel_color(0) == channels[0]
    assert theme.channel_color(n) == channels[0]
    assert theme.channel_color(n + 3) == channels[3]


def test_stylesheet_substitutes_every_placeholder() -> None:
    qss = theme.stylesheet()
    # No unsubstituted placeholder should survive; `substitute` would have
    # raised on a missing one, so what this catches is a stray `$`.
    assert not re.search(r"\$[a-z_]+", qss)
    assert theme.color("accent") in qss
    assert theme.color("surface.window") in qss


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


@pytest.mark.parametrize("token", TEXT_TOKENS)
@pytest.mark.parametrize("surface", SURFACE_TOKENS)
def test_text_contrast_meets_the_spec(token: str, surface: str) -> None:
    """Named by token, so a failure says which colour rather than which hex."""
    ratio = theme.contrast(theme.color(token), theme.color(surface))
    assert ratio >= 4.5, f"{token} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("colour", theme.BUILTIN.channels)
def test_channel_colours_are_legible_on_panels(colour: str) -> None:
    """04-ui-spec.md: channel colours must stay legible on surface.panel."""
    assert theme.contrast(colour, theme.color("surface.panel")) >= 3.0, colour


def test_accent_clears_the_ui_component_threshold() -> None:
    """`accent` is not text, but a playhead nobody can see is still a bug."""
    for surface in SURFACE_TOKENS:
        ratio = theme.contrast(theme.color("accent"), theme.color(surface))
        assert ratio >= 3.0, f"accent on {surface} is {ratio:.2f}:1"


def _variant(tokens: Mapping[str, str]) -> theme.Theme:
    """The built-in theme with some tokens given different values."""
    return replace(theme.BUILTIN, tokens={**theme.BUILTIN.tokens, **tokens})


def test_the_builtin_has_no_contrast_problems() -> None:
    """The default is *held* to the rule; a user's theme is only told about it."""
    assert theme.BUILTIN.contrast_problems() == []


def test_contrast_problems_names_every_failing_pair() -> None:
    """All of them, not the first: an author wants the list, not one a run."""
    problems = _variant({"text.primary": "#202020"}).contrast_problems()

    assert len(problems) == len(SURFACE_TOKENS)
    for surface in SURFACE_TOKENS:
        assert any(f"text.primary on {surface}" in line for line in problems), surface
    assert all(line.startswith("text.primary") for line in problems), problems


def test_contrast_problems_keeps_the_two_documented_exemptions() -> None:
    """`text.disabled` and `accent` are exempt, and stay exempt once it moves.

    A check that rediscovered them as failures would fire on every load of
    every theme including the built-in, and a report that is never empty is a
    report nobody reads.
    """
    invisible = _variant({"text.disabled": "#1A1A1A", "accent": "#1A1A1A"})
    assert invisible.contrast_problems() == []


def test_contrast_problems_skips_tokens_a_theme_does_not_define() -> None:
    """Completeness is the merge's job, not this rule's."""
    partial = theme.Theme(
        name="partial",
        tokens={"surface.panel": "#1F1F1F", "text.primary": "#CCCCCC"},
        channels=("#A855F7",),
    )
    assert partial.contrast_problems() == []


def test_the_contrast_vocabulary_cannot_go_empty() -> None:
    """A guard against a vacuous parametrization, not a second home for the lists.

    The parametrized tests above draw from `theme`'s own tuples, which is what
    stops the spec and the code drifting - and it also means emptying either
    tuple would produce zero cases and a green run. This asserts the shape
    rather than the contents, so it is not itself something that can drift.
    """
    assert len(theme.SURFACE_TOKENS) == 4
    assert len(theme.TEXT_TOKENS) == 5
    assert "text.disabled" not in theme.TEXT_TOKENS, "04 exempts it"
    assert "accent" not in theme.TEXT_TOKENS, "04 exempts it"


def test_surfaces_are_monotonic() -> None:
    """Deepest first, each step lighter; widgets rely on the ordering."""
    levels = [theme.luminance(theme.color(name)) for name in SURFACE_TOKENS]
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
    levels = [theme.luminance(colour) for colour in surfaces]
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


# --------------------------------------------------------------------------- #
# the stylesheet is built from groups, and changed no pixels doing it
# --------------------------------------------------------------------------- #

BEFORE_M9 = Path(__file__).resolve().parent / "fixtures" / "stylesheet_before_m9.qss"


def test_the_stylesheet_is_unchanged_by_the_indirection() -> None:
    """The cheapest possible proof that this phase changed no pixels.

    The fixture was captured and committed before a line of M9 was written,
    and the whole point is that it is *asserted* rather than regenerated. A
    regenerated golden file records whatever the code now does, which is not
    a test of anything.

    It is a migration check with an expiry. It retires the first time a
    milestone legitimately changes a colour in the sheet — in a commit that
    says which colour and why, which is exactly the conversation this is
    meant to force.
    """
    assert theme.stylesheet() == BEFORE_M9.read_text(encoding="utf-8")


def test_every_group_key_fills_exactly_one_placeholder() -> None:
    """The sheet and the vocabulary cover each other, with nothing spare.

    A placeholder with no group key behind it already fails loudly, because
    `substitute` raises. The other direction is the silent one: a group key
    nothing reads is a role that looks themeable and is not, and a theme
    author changing it would see no effect and no error.
    """
    sheet = resources.files("immersive.assets").joinpath("app.qss").read_text("utf-8")
    placeholders = set(re.findall(r"\$([a-z_0-9]+)", sheet))
    keys = {
        f"{group}.{key}".replace(".", "_")
        for group, values in theme.BUILTIN.groups.items()
        for key in values
    }
    assert placeholders == keys


def test_the_stylesheet_names_no_colour() -> None:
    """F-44, asserted on the file rather than on the rendered sheet.

    The sheet is where a hex would be easiest to slip in and hardest to
    notice — it is not Python, so nothing else here looks at it.
    """
    sheet = resources.files("immersive.assets").joinpath("app.qss").read_text("utf-8")
    assert not re.findall(r"#[0-9A-Fa-f]{6}", sheet)


def test_the_stylesheet_follows_the_theme_it_is_given() -> None:
    """A different theme renders a different sheet, without being made active."""
    recoloured = theme.Theme(
        name="Green",
        tokens={**theme.BUILTIN.tokens, "accent": "#00FF00"},
        channels=theme.BUILTIN.channels,
        groups=theme.BUILTIN.groups,
    )
    sheet = theme.stylesheet(recoloured)

    assert "#00FF00" in sheet
    assert "#A855F7" not in sheet, "the old accent survived somewhere"
    assert theme.stylesheet() != sheet, "the active theme was not the one asked for"


def test_no_widget_source_names_a_hex() -> None:
    """F-44, over the whole UI layer.

    The acceptance for this phase spells it as a grep; a test is the same
    grep that cannot be forgotten. `theme.py` holds the palette and is the
    one file allowed to say a colour out loud — and after this phase even it
    says them only inside the built-in theme.
    """
    ui = Path(theme.__file__).parent
    offenders = {
        str(path.relative_to(ui)): re.findall(
            r"#[0-9A-Fa-f]{6}", path.read_text("utf-8")
        )
        for path in sorted(ui.rglob("*.py"))
        if path.name != "theme.py"
    }
    assert not {name: hexes for name, hexes in offenders.items() if hexes}


# --------------------------------------------------------------------------- #
# the constants are gone, and the widgets followed
# --------------------------------------------------------------------------- #


def test_no_module_level_colour_constant_survives() -> None:
    """The goal of the phase, asserted rather than assumed.

    A constant left behind is a colour resolved once, when this module was
    first imported, which is the one thing D-76 forbids. Checked by looking
    at the module rather than by grepping the file, so a constant reintroduced
    under any name is caught.
    """
    colours = {
        name: value
        for name, value in vars(theme).items()
        if name.isupper() and isinstance(value, str) and HEX.match(value)
    }
    assert not colours, f"colour constants back on the module: {colours}"


def test_the_only_place_a_hex_appears_is_the_built_in_theme() -> None:
    """F-44 at its strongest: even `theme.py` says colours in exactly one place.

    Every hex in this module's source has to be inside `BUILTIN` — its
    thirteen tokens and its eight channel colours, twenty-one in all. A hex
    anywhere else in the file is a colour that no theme can replace, which is
    the failure this milestone exists to prevent, one file earlier than
    anybody would look for it.
    """
    source = Path(theme.__file__).read_text(encoding="utf-8")
    found = re.findall(r"#[0-9A-Fa-f]{6}", source)
    expected = list(theme.BUILTIN.tokens.values()) + list(theme.BUILTIN.channels)

    assert sorted(found) == sorted(expected), "a hex outside the built-in theme"


@pytest.mark.gui
def test_a_widget_built_under_a_new_theme_wears_it() -> None:
    """The assertion the module constants could never have passed.

    A widget that baked its colour in at import would go on painting the old
    theme's grey no matter what was switched, and it would do it silently.
    This is the property the milestone's last phase is built on; it costs one
    test here and four phases of confusion if it is left until then.
    """
    from immersive.app import build_application
    from immersive.ui.widgets.placeholder import Placeholder

    build_application([])

    before = Placeholder("Pool").styleSheet()
    assert theme.color("surface.panel") in before

    theme.use(
        theme.Theme(
            name="Green",
            tokens={**theme.BUILTIN.tokens, "surface.panel": "#00FF00"},
            channels=theme.BUILTIN.channels,
            groups=theme.BUILTIN.groups,
        )
    )

    assert "#00FF00" in Placeholder("Pool").styleSheet()
