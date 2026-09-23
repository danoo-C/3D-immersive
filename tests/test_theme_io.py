"""`.3dimtheme` is read, merged over a default, and never raises.

The schema is 04-ui-spec.md's; this file holds it to it. Nothing here needs
Qt: `theme_io` reads JSON and builds a `Theme`, and both are headless.
"""

from __future__ import annotations

import json
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
