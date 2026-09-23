"""`.3dimtheme` is read, merged over a default, and never raises.

The schema is 04-ui-spec.md's; this file holds it to it. Nothing here needs
Qt: `theme_io` reads JSON and builds a `Theme`, and both are headless.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from immersive.ui import theme, theme_io


def written(**document: Any) -> str:
    """A theme file's text, with the schema version filled in."""
    return json.dumps({"schema_version": theme_io.SCHEMA_VERSION, **document})


# --------------------------------------------------------------------------- #
# the merge
# --------------------------------------------------------------------------- #


def test_a_well_formed_theme_reports_nothing() -> None:
    report = theme_io.loads(written(name="Quiet", tokens={"accent": "#FF0000"}))
    assert report.problems == []
    assert report.applied
    assert report.theme.name == "Quiet"


def test_a_partial_theme_merges() -> None:
    """The acceptance line: two lines of JSON, and one colour changes.

    This is the property D-45 exists for. A theme that replaced the palette
    wholesale would break on every release that added a token.
    """
    report = theme_io.loads(written(tokens={"accent": "#FF0000"}))

    assert report.theme.token("accent") == "#FF0000"
    untouched = {
        name: value
        for name, value in theme.BUILTIN.tokens.items()
        if name != "accent"
    }
    assert {
        name: report.theme.token(name) for name in untouched
    } == untouched
    assert report.theme.channels == theme.BUILTIN.channels
    assert report.theme.groups == theme.BUILTIN.groups


def test_a_group_value_resolves_against_a_token_only_the_default_defines() -> None:
    """The case that makes partial themes actually work.

    The file names `surface.hover` and never defines it. Tokens are merged
    before group values are checked, so it resolves against the built-in
    rather than being reported as naming nothing.
    """
    report = theme_io.loads(written(groups={"focus": {"ring": "surface.hover"}}))

    assert report.problems == []
    assert report.theme.value("focus", "ring") == theme.BUILTIN.token(
        "surface.hover"
    )


def test_one_group_key_leaves_the_rest_of_the_group_alone() -> None:
    """Merged a level below the group, or a partial theme is not partial."""
    report = theme_io.loads(written(groups={"button": {"background": "error"}}))

    assert report.theme.value("button", "background") == theme.BUILTIN.token("error")
    for key in theme.BUILTIN.groups["button"]:
        if key == "background":
            continue
        assert report.theme.value("button", key) == theme.BUILTIN.value(
            "button", key
        )


def test_a_group_value_may_be_a_literal() -> None:
    """The escape hatch: one thing breaks the family, on purpose."""
    report = theme_io.loads(written(groups={"focus": {"ring": "#00FF00"}}))

    assert report.problems == []
    assert report.theme.value("focus", "ring") == "#00FF00"


def test_channels_are_replaced_wholesale_not_merged_by_index() -> None:
    """D-75: the channel list is a sequence, and its indices are not keys.

    Merging per index would make the palette's length unthemeable, so a
    four-colour theme could not exist.
    """
    report = theme_io.loads(written(channels=["#111111", "#222222"]))

    assert report.problems == []
    assert report.theme.channels == ("#111111", "#222222")
    assert report.theme.channel(2) == "#111111", "and it still wraps"


def test_the_merge_target_is_a_parameter() -> None:
    """Phase 3 loads the built-in theme through this same path (D-47).

    A reader that can only merge over the one theme it imports has nothing to
    load the built-in *as*, so the door is held open here rather than
    unpicked there.
    """
    other = theme.Theme(
        name="Other",
        tokens={"accent": "#0000FF", "surface.panel": "#FFFFFF"},
        channels=("#0000FF",),
        groups={"panel": {"background": "surface.panel"}},
    )
    report = theme_io.loads(written(tokens={"accent": "#FF0000"}), over=other)

    assert report.theme.token("accent") == "#FF0000"
    assert report.theme.token("surface.panel") == "#FFFFFF"
    assert "text.primary" not in report.theme.tokens, "BUILTIN did not leak in"


# --------------------------------------------------------------------------- #
# the vocabulary is closed
# --------------------------------------------------------------------------- #


def test_a_theme_cannot_introduce_a_token() -> None:
    """04's *Precedence*: a theme revalues a token, it does not add one."""
    report = theme_io.loads(written(tokens={"my.purple": "#FF00FF"}))

    assert "my.purple" not in report.theme.tokens
    assert len(report.problems) == 1
    assert report.problems[0].where == "tokens.my.purple"
    assert report.problems[0].severity is theme_io.Severity.WARN


def test_a_token_a_theme_invented_is_reported_twice_and_the_first_explains() -> None:
    """Two true statements about one mistake, and the order matters.

    The token is dropped as unknown; the group value that named it is then
    dangling and falls back. `project_io` met the same shape and its answer
    holds - each message names what it saw - provided the first one says the
    vocabulary is fixed, which is the sentence that explains the second.
    """
    report = theme_io.loads(
        written(
            tokens={"my.purple": "#FF00FF"},
            groups={"focus": {"ring": "my.purple"}},
        )
    )

    assert [problem.where for problem in report.problems] == [
        "tokens.my.purple",
        "groups.focus.ring",
    ]
    assert "cannot add one" in report.problems[0].message
    assert report.theme.value("focus", "ring") == theme.BUILTIN.value("focus", "ring")


# --------------------------------------------------------------------------- #
# names, and the file on disk
# --------------------------------------------------------------------------- #


def test_a_theme_with_no_name_is_called_after_its_file(tmp_path: Path) -> None:
    """A picker lists themes by name, and every unnamed one being called
    "VS Code Dark" would make the list useless."""
    path = tmp_path / "ocean.3dimtheme"
    path.write_text(written(tokens={"accent": "#0088FF"}), encoding="utf-8")

    report = theme_io.load(path)

    assert report.problems == []
    assert report.theme.name == "ocean"
    assert report.source == path


def test_a_name_that_is_present_and_unusable_is_reported() -> None:
    """Absent is fine - `name` is optional. Typed and empty is not."""
    report = theme_io.loads(written(name=""), source=Path("ocean.3dimtheme"))

    assert [problem.where for problem in report.problems] == ["name"]
    assert report.theme.name == "ocean"


def test_author_survives_the_read() -> None:
    """04's file example carries one, so the object has to hold one."""
    report = theme_io.loads(written(name="Quiet", author="somebody"))

    assert report.problems == []
    assert report.theme.author == "somebody"


def test_load_reads_a_file_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "red.3dimtheme"
    path.write_text(
        written(name="Red", tokens={"accent": "#FF0000"}), encoding="utf-8"
    )

    report = theme_io.load(path)

    assert report.applied
    assert report.theme.name == "Red"
    assert report.theme.token("accent") == "#FF0000"


@pytest.mark.parametrize(
    "value", ["not a colour", "#FFF", "#GGGGGG", 7, None, ["#FF0000"]]
)
def test_a_token_value_that_is_not_a_colour_falls_back(value: object) -> None:
    report = theme_io.loads(written(tokens={"accent": value}))

    assert report.theme.token("accent") == theme.BUILTIN.token("accent")
    assert [problem.where for problem in report.problems] == ["tokens.accent"]


# --------------------------------------------------------------------------- #
# the writer
# --------------------------------------------------------------------------- #


def test_a_theme_round_trips() -> None:
    report = theme_io.loads(theme_io.dumps(theme.BUILTIN))

    assert report.problems == []
    assert report.theme == theme.BUILTIN


def test_the_written_file_is_the_shape_04_describes() -> None:
    """Asserted over the text, not over a round trip.

    M1 phase 5 spent three of its four surviving mutations on this one
    lesson: a round trip proves the reader and the writer *agree*, not that
    either is right. Both can be wrong in the same direction and the trip
    still closes. So this reads the file.
    """
    document = json.loads(theme_io.dumps(theme.BUILTIN))

    assert set(document) == {
        "schema_version",
        "name",
        "author",
        "tokens",
        "channels",
        "groups",
    }
    assert document["schema_version"] == theme_io.SCHEMA_VERSION
    assert document["name"] == "VS Code Dark"
    assert document["tokens"] == dict(theme.BUILTIN.tokens)
    assert document["channels"] == list(theme.BUILTIN.channels)
    assert document["groups"]["button"] == dict(theme.BUILTIN.groups["button"])


def test_the_written_file_sorts_its_keys() -> None:
    """D-13: a format meant to live in git does not churn its own diff."""
    text = theme_io.dumps(theme.BUILTIN)

    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
    assert text.endswith("\n")


def test_writing_what_was_read_reproduces_the_file() -> None:
    """The assertion a round trip cannot make on its own.

    Equality of objects survives a reader and a writer that drop the same key.
    Equality of *text* does not.
    """
    text = theme_io.dumps(theme.BUILTIN)

    assert theme_io.dumps(theme_io.loads(text).theme) == text


def test_the_written_file_is_readable_by_a_person() -> None:
    """Indented, one key a line: it is a file somebody is expected to edit."""
    text = theme_io.dumps(theme.BUILTIN)

    assert '\n  "tokens": {\n' in text
    assert f'    "accent": "{theme.BUILTIN.token("accent")}"' in text


def test_save_then_load(tmp_path: Path) -> None:
    path = tmp_path / "builtin.3dimtheme"
    theme_io.save(theme.BUILTIN, path)

    report = theme_io.load(path)

    assert report.problems == []
    assert report.theme == theme.BUILTIN
    assert path.read_text(encoding="utf-8") == theme_io.dumps(theme.BUILTIN)


def test_a_theme_that_is_not_the_builtin_round_trips() -> None:
    """The round trip must not be a property of BUILTIN in particular."""
    original = theme_io.loads(
        written(
            name="Ocean",
            author="somebody",
            tokens={"accent": "#0088FF"},
            channels=["#0088FF", "#00CCAA"],
            groups={"focus": {"ring": "#00FF00"}},
        )
    ).theme

    assert theme_io.loads(theme_io.dumps(original)).theme == original


# --------------------------------------------------------------------------- #
# 04's failure table, row by row
# --------------------------------------------------------------------------- #
#
# Every row of *When a theme is wrong* gets a test, and each asserts the same
# two things: a usable theme comes back, and the problem is named. The row
# that says "never fatally" is not any one of these - it is a property of the
# whole set, and it is asserted as one at the foot of this section.


def test_a_missing_file_is_reported(tmp_path: Path) -> None:
    report = theme_io.load(tmp_path / "nothing.3dimtheme")

    assert report.theme == theme.BUILTIN
    assert not report.applied
    assert report.problems[0].severity is theme_io.Severity.ERROR


def test_a_file_that_cannot_be_read_is_reported(tmp_path: Path) -> None:
    """A directory, which every platform refuses to read as a file."""
    directory = tmp_path / "themes.3dimtheme"
    directory.mkdir()

    report = theme_io.load(directory)

    assert report.theme == theme.BUILTIN
    assert not report.applied


def test_a_file_that_is_not_utf8_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "bad.3dimtheme"
    path.write_bytes(b'{"schema_version": 1, "name": "\xff\xfe"}')

    report = theme_io.load(path)

    assert report.theme == theme.BUILTIN
    assert not report.applied
    assert "UTF-8" in report.problems[0].message


def test_malformed_json_is_reported_with_the_parse_error() -> None:
    report = theme_io.loads('{"schema_version": 1, "tokens": {')

    assert report.theme == theme.BUILTIN
    assert not report.applied
    # 04: "reported with the parse error" - so the line and column are in it.
    assert "line" in report.problems[0].where
    assert "column" in report.problems[0].where


@pytest.mark.parametrize("text", ["[]", '"a theme"', "7", "null", "true"])
def test_valid_json_that_is_not_an_object_is_reported(text: str) -> None:
    report = theme_io.loads(text)

    assert report.theme == theme.BUILTIN
    assert not report.applied


def test_an_unknown_group_is_ignored_and_reported() -> None:
    report = theme_io.loads(written(groups={"spaceship": {"hull": "#FF0000"}}))

    assert "spaceship" not in report.theme.groups
    assert [problem.where for problem in report.problems] == ["groups.spaceship"]
    assert report.applied, "a theme with one odd group is still a theme"


def test_an_unknown_key_inside_a_known_group_is_ignored_and_reported() -> None:
    report = theme_io.loads(written(groups={"button": {"sparkle": "#FF0000"}}))

    assert "sparkle" not in report.theme.groups["button"]
    assert [problem.where for problem in report.problems] == ["groups.button.sparkle"]


def test_a_group_value_naming_nothing_falls_back_and_is_reported() -> None:
    report = theme_io.loads(written(groups={"focus": {"ring": "nonsense"}}))

    assert report.theme.value("focus", "ring") == theme.BUILTIN.value("focus", "ring")
    assert [problem.where for problem in report.problems] == ["groups.focus.ring"]


def test_a_missing_schema_version_is_reported() -> None:
    report = theme_io.loads(json.dumps({"tokens": {"accent": "#FF0000"}}))

    assert report.theme == theme.BUILTIN
    assert not report.applied
    assert report.problems[0].where == "schema_version"


@pytest.mark.parametrize("version", ["1", 1.0, True, None, [1]])
def test_a_schema_version_that_is_not_a_whole_number_is_reported(
    version: object,
) -> None:
    """`True` is in that list deliberately: in Python it is an `int`."""
    report = theme_io.loads(json.dumps({"schema_version": version}))

    assert report.theme == theme.BUILTIN
    assert not report.applied


def test_a_newer_schema_keeps_what_it_recognises_and_says_so() -> None:
    """Where this and `project_io` part company, and it is deliberate.

    A .3dim is the work and refusing a newer one is right. A .3dimtheme is
    cosmetic, and the worst case of a partial load is the wrong shade of grey.
    """
    report = theme_io.loads(
        json.dumps(
            {
                "schema_version": theme_io.SCHEMA_VERSION + 1,
                "tokens": {"accent": "#FF0000"},
                "constellations": {"orion": True},
            }
        )
    )

    assert report.theme.token("accent") == "#FF0000", "what it recognised"
    assert report.applied
    versions = [p for p in report.problems if p.where == "schema_version"]
    assert len(versions) == 1
    assert versions[0].severity is theme_io.Severity.WARN


def test_a_schema_too_old_to_migrate_is_reported() -> None:
    """MIGRATIONS is empty, so schema 0 has no route forward. It says so."""
    report = theme_io.loads(json.dumps({"schema_version": 0}))

    assert report.theme == theme.BUILTIN
    assert not report.applied
    assert "migration" in report.problems[0].message


#: One of every row above, plus a few shapes nobody sensible would write.
HOSTILE = [
    "",
    "{",
    "[]",
    "null",
    "not json at all",
    '{"schema_version": 1}',
    '{"schema_version": 0}',
    '{"schema_version": 99}',
    '{"schema_version": "1"}',
    '{"tokens": {"accent": "#FF0000"}}',
    '{"schema_version": 1, "tokens": null}',
    '{"schema_version": 1, "tokens": {"accent": null}}',
    '{"schema_version": 1, "tokens": {"": ""}}',
    '{"schema_version": 1, "channels": []}',
    '{"schema_version": 1, "channels": "#FF0000"}',
    '{"schema_version": 1, "channels": [null, 7, {}]}',
    '{"schema_version": 1, "groups": []}',
    '{"schema_version": 1, "groups": {"button": null}}',
    '{"schema_version": 1, "groups": {"button": {"background": 7}}}',
    '{"schema_version": 1, "groups": {"button": {"background": "channel"}}}',
    '{"schema_version": 1, "name": null, "author": 7}',
]


@pytest.mark.parametrize("text", HOSTILE)
def test_no_theme_file_can_raise(text: str) -> None:
    """The acceptance line, and it is a property of the set, not of a row.

    F-47 and D-48: a typo in a cosmetic file must not stand between somebody
    and their project. A caller that never looks at `problems` still gets a
    theme it can paint with.
    """
    report = theme_io.loads(text)

    assert isinstance(report.theme, theme.Theme)
    assert report.theme.problems() == [], "and it is a theme that resolves"
    # The assertion that actually bites. A theme can be well-formed and still
    # be one the application cannot paint with, and "never fatally" is a
    # promise about startup rather than about construction.
    assert theme.stylesheet(report.theme)


@pytest.mark.parametrize("text", HOSTILE)
def test_no_theme_file_can_raise_from_disk(text: str, tmp_path: Path) -> None:
    """The same set through `load`, because that path has its own failures."""
    path = tmp_path / "hostile.3dimtheme"
    path.write_text(text, encoding="utf-8")

    assert isinstance(theme_io.load(path).theme, theme.Theme)


# --------------------------------------------------------------------------- #
# the reserved `channel` value
# --------------------------------------------------------------------------- #


def test_channel_is_refused_where_nothing_is_painted_per_channel() -> None:
    """A theme must not be able to stop the application painting.

    `Theme.value` raises on a `channel` value rather than inventing a channel
    to resolve it against, and `stylesheet()` asks for every group key there
    is. So a file setting one QSS-backed key to `channel` would take startup
    down - which is the one thing F-47 says a cosmetic file must never do.
    Nothing in the built-in paints per channel yet; M3 draws the first.
    """
    report = theme_io.loads(
        written(groups={"button": {"background": theme.CHANNEL}})
    )

    assert [problem.where for problem in report.problems] == [
        "groups.button.background"
    ]
    assert report.theme.value("button", "background") == theme.BUILTIN.value(
        "button", "background"
    )
    assert theme.stylesheet(report.theme), "and startup survives"


def test_channel_is_kept_where_the_default_paints_per_channel() -> None:
    """The rule is "where the default already does", not "never".

    Asserted against a merge target that has such a key, because the built-in
    will not have one until M3 - and a rule tested only in the direction that
    refuses is a rule that could simply be a refusal.
    """
    over = theme.Theme(
        name="With clips",
        tokens={"accent": "#A855F7"},
        channels=("#A855F7",),
        groups={"clip": {"body": theme.CHANNEL, "selected.border": "accent"}},
    )

    kept = theme_io.loads(
        written(groups={"clip": {"body": theme.CHANNEL}}), over=over
    )
    assert kept.problems == []
    assert kept.theme.groups["clip"]["body"] == theme.CHANNEL

    moved = theme_io.loads(
        written(groups={"clip": {"selected.border": theme.CHANNEL}}), over=over
    )
    assert [problem.where for problem in moved.problems] == [
        "groups.clip.selected.border"
    ]


# --------------------------------------------------------------------------- #
# contrast, reported and never enforced
# --------------------------------------------------------------------------- #


def test_a_theme_with_poor_contrast_loads_anyway() -> None:
    """04: *Contrast is checked, not enforced*.

    Refusing somebody's own theme on their own machine is not a call this
    application gets to make. So the theme applies, and the report says so.
    """
    report = theme_io.loads(written(tokens={"text.primary": "#202020"}))

    assert report.applied
    assert report.theme.token("text.primary") == "#202020"
    assert all(
        problem.severity is theme_io.Severity.WARN for problem in report.problems
    )


def test_every_failing_contrast_pair_is_reported_not_just_the_first() -> None:
    """An author fixing a palette wants the list, not one item a run."""
    report = theme_io.loads(written(tokens={"text.primary": "#202020"}))

    contrast = [p for p in report.problems if p.where == "contrast"]
    assert len(contrast) == len(theme.SURFACE_TOKENS)
    for surface in theme.SURFACE_TOKENS:
        assert any(f"on {surface}" in p.message for p in contrast), surface


def test_a_theme_with_good_contrast_reports_none() -> None:
    """The built-in merged over itself must be silent, or the report is noise."""
    assert theme_io.loads(theme_io.dumps(theme.BUILTIN)).problems == []


# --------------------------------------------------------------------------- #
# 04's own worked example
# --------------------------------------------------------------------------- #

SPEC = Path(__file__).resolve().parent.parent / "docs" / "04-ui-spec.md"


def spec_example() -> str:
    """The `.3dimtheme` listing from the *Theming* section of 04.

    Lifted out of the document rather than copied into this file, for the
    reason M1 phase 5 added the same test for `03`: that block is the first
    thing anybody implementing against this format reads, and nothing had
    ever opened it. `03`'s turned out not to load.
    """
    text = SPEC.read_text(encoding="utf-8")
    section = re.search(r"### The file\n(.*?)\n### ", text, re.S)
    assert section, "04-ui-spec.md no longer has a *The file* section"
    block = re.search(r"```json\n(.*?)```", section.group(1), re.S)
    assert block, "04-ui-spec.md's *The file* section has no JSON listing"
    return block.group(1)


def test_the_specifications_own_example_is_a_file_this_module_opens() -> None:
    report = theme_io.loads(spec_example())

    assert report.applied
    assert report.theme.name == "VS Code Dark"


def test_the_specifications_own_example_is_the_built_in_theme() -> None:
    """The example is not merely loadable, it is *the default*.

    Its tokens, its channels and its `button` group are the built-in's, key
    for key - so merging it over the built-in has to come back to exactly the
    built-in. A colour edited in the document and not in `theme.py` fails
    here, which is the drift this kind of test exists to catch.
    """
    assert theme_io.loads(spec_example()).theme == theme.BUILTIN


def test_the_example_only_reports_groups_no_milestone_has_built_yet() -> None:
    """The example is forward-looking, and that is allowed - but say which.

    `timeline` and `clip` belong to M3 by 04's own ownership table. If a
    *third* group shows up here, either the example grew a group nobody owns
    or M9 dropped one it was supposed to build.
    """
    problems = theme_io.loads(spec_example()).problems

    assert [problem.where for problem in problems] == [
        "groups.timeline",
        "groups.clip",
    ]
    assert all(p.severity is theme_io.Severity.WARN for p in problems)
