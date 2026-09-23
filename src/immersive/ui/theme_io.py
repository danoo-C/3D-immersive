"""`.3dimtheme` - reading a theme file, and saying what was wrong with it.

The schema is owned by the *Theming* section of docs/04-ui-spec.md. This
module implements it (D-77), and it is the only thing in `ui/` that reads a
file the user wrote.

**Nothing here raises.** A theme file is cosmetic, and a typo in one must not
stand between somebody and their project (F-47, D-48). Every failure in 04's
*When a theme is wrong* table comes back as a problem in the report, and the
caller is always handed a usable `Theme` - the merge target, untouched, when
the file yielded nothing at all.

That is the half of the split `theme.py` does not do. `Theme` validates at
construction and *does* raise, because the built-in theme is code and a group
of it naming a token that does not exist is a bug that must not ship. So this
module drops what it cannot use, records it, and hands `Theme` something
already known to be well-formed. One rule, two audiences.

**The token vocabulary is closed.** A theme file may give a new value to a
token the merge target defines; it cannot introduce one, because a `tokens`
entry nobody knows is an unknown key and 04 says unknown keys are ignored and
reported. That is what makes a partial theme survive a release that adds
colours, and it is why a file defining its own token and then naming it from
a group is reported twice - once for the token, once for the group value that
is now dangling. Both messages are true, each names what it saw, and the
first explains the second.

⚠️ **A newer `schema_version` loads here and is refused by `project_io`**, and
the difference is deliberate rather than an oversight in one of them. A
`.3dim` *is the work*: opening one by ignoring the parts this build does not
understand means silently discarding somebody's automation and then offering
to save over the file it came from. A `.3dimtheme` is cosmetic, holds nothing
that cannot be retyped, and is never written back by the application. The
worst case of a partial theme load is the wrong shade of grey.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any, Final

from immersive.ui.theme import BUILTIN, CHANNEL, Theme, ThemeError, is_colour

#: The on-disk schema this build writes, and what drives forward migration on
#: load. Same discipline as `.3dim` - see docs/03-data-model.md.
SCHEMA_VERSION: Final = 1

#: `version -> migrate to version + 1`. Empty, and deliberately present:
#: nothing has shipped, so there is no older theme file in the world to
#: migrate from. The hook exists now so that the first real migration is not
#: also the change that introduces migrations, which is `project_io.py`'s
#: reasoning and holds here for the same reason.
MIGRATIONS: Final[dict[int, Callable[[dict[str, Any]], dict[str, Any]]]] = {}


class Severity(StrEnum):
    """How loudly a problem should be shown (D-78).

    The three values docs/04-ui-spec.md's *Notices* section already defines,
    taken from there rather than invented here so that M9 phase 4 - which
    builds `ui/widgets/notices.py` and has to colour a status line from
    exactly this - cannot end up with a second, incompatible idea of what a
    warning is. This enum is expected to move there when that surface exists.
    """

    #: Something the user asked for did not happen: the file yielded no theme.
    ERROR = "error"
    #: It happened, with a caveat: a theme with one key missing out of it.
    WARN = "warn"
    #: It happened.
    INFO = "info"


@dataclass(frozen=True)
class ThemeProblem:
    """One thing wrong with a theme file, where it was, and how loud it is.

    Not `core.model.Problem`, which is the obvious reuse and cannot answer
    the question the notice centre asks of everything it is handed (D-78):
    that type carries a `where` and a `message`, and its own docstring says
    it is one reason a *project* is not well-formed.
    """

    where: str
    message: str
    severity: Severity

    def __str__(self) -> str:
        return f"{self.where}: {self.message}" if self.where else self.message


@dataclass(frozen=True)
class ThemeReport:
    """A usable theme, and everything that was wrong with the file it came from.

    `theme` is never `None` and never half-built. When the file yielded
    nothing the merge target comes back untouched, so a caller that ignores
    `problems` entirely still paints something correct - which is what F-47
    asks for and the reason this is not an exception.
    """

    theme: Theme
    source: Path | None
    problems: list[ThemeProblem]

    @property
    def applied(self) -> bool:
        """Whether the file contributed anything at all.

        The distinction phase 4's notice line needs: *"your theme is loaded,
        with two keys ignored"* and *"your theme is not loaded"* are different
        sentences, and only the severity of the problems tells them apart.
        """
        return not any(
            problem.severity is Severity.ERROR for problem in self.problems
        )


class _Reading:
    """One pass over a parsed theme, and the problems it found.

    An object rather than a list threaded through six functions, for
    `project_io._Reading`'s reason: every reader below needs somewhere to
    record what it dropped, and passing a list into each of them is the kind
    of noise that gets forgotten at one call site and noticed by nobody.

    Lenient all the way through. Nothing here decides a file is hopeless
    except `loads`, and it only does so before any of this runs.
    """

    def __init__(self) -> None:
        self.problems: list[ThemeProblem] = []

    def error(self, where: str, message: str) -> None:
        self.problems.append(ThemeProblem(where, message, Severity.ERROR))

    def warn(self, where: str, message: str) -> None:
        self.problems.append(ThemeProblem(where, message, Severity.WARN))


def _shown(value: Any) -> str:
    """A value as a message should carry it.

    The type on its own - "accent is not a colour" - does not say what was
    typed, and a theme author fixing a palette is looking for the thing they
    typed. Truncated, because a token's value can be a whole nested object in
    a file somebody got badly wrong.
    """
    shown = repr(value)
    return shown if len(shown) <= 40 else f"{shown[:37]}..."


def _kind(value: Any) -> str:
    """The JSON name for a value's type, for a message about shape."""
    return {
        dict: "object",
        list: "array",
        str: "string",
        bool: "boolean",
        int: "number",
        float: "number",
        type(None): "null",
    }.get(type(value), type(value).__name__)


# --------------------------------------------------------------------------- #
# the pieces
# --------------------------------------------------------------------------- #


def _versioned(
    reading: _Reading, document: dict[str, Any]
) -> dict[str, Any] | None:
    """`document`, brought up to `SCHEMA_VERSION`. `None` if it cannot be.

    Read before anything else is parsed, for the reason `project_io` reads it
    first: a file from a schema this build does not know would otherwise fail
    somewhere deep inside a key that changed meaning, and the report would
    describe the symptom rather than the cause.

    A *newer* file is kept rather than refused, which is where this and
    `project_io` part company - see the module docstring.
    """
    if "schema_version" not in document:
        reading.error(
            "schema_version",
            "is missing, and a theme has to say which schema it was written with",
        )
        return None

    version = document["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        reading.error(
            "schema_version", f"is {_shown(version)}, not a whole number"
        )
        return None

    if version > SCHEMA_VERSION:
        reading.warn(
            "schema_version",
            f"is {version} and this build reads {SCHEMA_VERSION}; "
            f"keeping the parts it recognises",
        )
        return document

    while version < SCHEMA_VERSION:
        migrate = MIGRATIONS.get(version)
        if migrate is None:
            reading.error(
                "schema_version", f"there is no migration from schema {version}"
            )
            return None
        document = migrate(document)
        version += 1
    return document


def _name(reading: _Reading, document: dict[str, Any], fallback: str) -> str:
    """What this theme is called, for a picker to list it by.

    Absent is not a problem - `name` is optional, and a file called
    `ocean.3dimtheme` has already said what it is. Present and unusable is,
    because somebody typed it.
    """
    if "name" not in document:
        return fallback
    given = document["name"]
    if not isinstance(given, str) or not given:
        reading.warn("name", f"is {_shown(given)}, not a name; using {fallback!r}")
        return fallback
    return given


def _author(reading: _Reading, document: dict[str, Any]) -> str:
    if "author" not in document:
        return ""
    given = document["author"]
    if not isinstance(given, str):
        reading.warn("author", f"is a JSON {_kind(given)}, not a string; ignored")
        return ""
    return given


def _tokens(reading: _Reading, node: Any, over: Theme) -> dict[str, str]:
    """The merge target's tokens, with the file's accepted values over them."""
    merged = dict(over.tokens)
    if node is None:
        return merged
    if not isinstance(node, dict):
        reading.warn("tokens", f"is a JSON {_kind(node)}, not an object; ignored")
        return merged

    for name, value in node.items():
        if name not in over.tokens:
            reading.warn(
                f"tokens.{name}",
                "is not a token this build knows. A theme may give a token a "
                "new value and cannot add one, so this is ignored",
            )
            continue
        if not isinstance(value, str) or not is_colour(value):
            reading.warn(
                f"tokens.{name}",
                f"is {_shown(value)}, not a #RRGGBB colour; keeping the default",
            )
            continue
        merged[name] = value
    return merged


def _channels(reading: _Reading, node: Any, over: Theme) -> tuple[str, ...]:
    """The channel palette, replaced wholesale rather than merged by index.

    D-75 says what the channel list is: an ordered sequence indexed by
    position, not a set of keys. Merging it per index would treat those
    indices as keys - which is the thing D-75 says they are not - and would
    also make the palette's *length* unthemeable, so nobody could ship a
    four-colour theme. A file that gives channels gives all of them.
    """
    if node is None:
        return over.channels
    if not isinstance(node, list):
        reading.warn("channels", f"is a JSON {_kind(node)}, not an array; ignored")
        return over.channels

    kept: list[str] = []
    for index, value in enumerate(node):
        if not isinstance(value, str) or not is_colour(value):
            reading.warn(
                f"channels[{index}]",
                f"is {_shown(value)}, not a #RRGGBB colour; dropped",
            )
            continue
        kept.append(value)

    if not kept:
        reading.warn(
            "channels", "has no usable colour in it; keeping the default palette"
        )
        return over.channels
    return tuple(kept)


def _groups(
    reading: _Reading, node: Any, over: Theme, tokens: dict[str, str]
) -> dict[str, dict[str, str]]:
    """The merge target's groups, key by key, with the file's accepted values.

    Merged one level *below* the group, which is the whole point: a file that
    sets `button.background` and nothing else has to keep the other eight
    button keys, or a partial theme is only partial in the sentence that
    describes it.

    `tokens` is the already-merged map rather than the file's, and that
    ordering is what makes the phase's hardest acceptance line work: a group
    value naming a token the file does not define, but the default does,
    resolves against the default.

    The reserved `channel` value is accepted only for a key the merge target
    already paints per channel. Nothing does today - M3 draws the first one -
    so today it is accepted nowhere, and that is the point rather than a
    limitation.
    """
    merged = {name: dict(values) for name, values in over.groups.items()}
    if node is None:
        return merged
    if not isinstance(node, dict):
        reading.warn("groups", f"is a JSON {_kind(node)}, not an object; ignored")
        return merged

    for group, values in node.items():
        if group not in over.groups:
            reading.warn(
                f"groups.{group}", "is not a group this build draws; ignored"
            )
            continue
        if not isinstance(values, dict):
            reading.warn(
                f"groups.{group}",
                f"is a JSON {_kind(values)}, not an object; ignored",
            )
            continue

        for key, raw in values.items():
            where = f"groups.{group}.{key}"
            if key not in over.groups[group]:
                reading.warn(where, "is not a key this group has; ignored")
                continue
            if not isinstance(raw, str):
                reading.warn(
                    where,
                    f"is a JSON {_kind(raw)}, not a token name or a colour; "
                    f"keeping the default",
                )
                continue
            if raw == CHANNEL:
                # Only where the merge target already paints per channel.
                # Anywhere else there is no channel to resolve against, and
                # `Theme.value` raises rather than inventing one - so a
                # five-line theme file would stop the application painting,
                # which is exactly what F-47 forbids.
                if over.groups[group].get(key) != CHANNEL:
                    reading.warn(
                        where,
                        f"is {CHANNEL!r}, which means a channel's own colour "
                        f"and only resolves for a key that is painted once "
                        f"per channel; keeping the default",
                    )
                    continue
            elif not is_colour(raw) and raw not in tokens:
                reading.warn(where, f"names no token {raw!r}; keeping the default")
                continue
            merged[group][key] = raw
    return merged


# --------------------------------------------------------------------------- #
# the built-in theme, which is code
# --------------------------------------------------------------------------- #

#: The bundled default, reached through importlib.resources and never by
#: walking up from __file__ (D-30).
_THEME_PACKAGE: Final = "immersive.assets.themes"
_BUILTIN_FILE: Final = "vscode_dark.3dimtheme"


def _object(document: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    """`document[key]` as a mapping, or a `ThemeError` saying what it was."""
    value = document.get(key, {})
    if not isinstance(value, dict):
        raise ThemeError(
            f"{where} is not a theme this build can use",
            [f"{key}: is a JSON {_kind(value)}, not an object"],
        )
    return value


def _strings(values: dict[str, Any], prefix: str, where: str) -> dict[str, str]:
    """Every value is a string, or a `ThemeError` naming the one that is not.

    `Theme.problems()` would otherwise be handed an int and ask a regular
    expression to match it, and a `TypeError` from inside a validator says
    nothing about which key somebody got wrong.
    """
    for key, value in values.items():
        if not isinstance(value, str):
            raise ThemeError(
                f"{where} is not a theme this build can use",
                [f"{prefix}{key}: is a JSON {_kind(value)}, not a string"],
            )
    return dict(values)


def strict(text: str, *, source: str = "the theme") -> Theme:
    """Read a theme that is **code**, and raise on anything wrong with it.

    The other half of the split that runs through this milestone. `loads()`
    drops what it cannot use and reports, because a user's theme is input and
    a typo in a cosmetic file must not stand between somebody and their
    project. This reads a theme that ships *inside the wheel*, where the same
    typo is a bug that must not reach anybody - so it raises, on the
    developer's machine, in a test.

    It cannot go through `loads()`, and the reason is structural rather than
    stylistic: `loads()` filters every key against a merge target's
    vocabulary, and a theme read by this function **is** that vocabulary.
    There is nothing to merge it over and nothing to validate it against
    except itself - which turns out to be enough. `Theme` refuses a group
    naming a token the file does not define, `stylesheet()` refuses a
    vocabulary too short to render `app.qss`, and `contrast_problems()`
    refuses a default that breaks 4.5:1.

    A `schema_version` that is merely *different* is refused rather than
    migrated. A bundled theme ships with the build that reads it, so the two
    disagreeing is not an old file in the world, it is a build that was put
    together wrong.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as broken:
        raise ThemeError(
            f"{source} is not valid JSON",
            [f"line {broken.lineno}, column {broken.colno}: {broken.msg}"],
        ) from broken

    if not isinstance(document, dict):
        raise ThemeError(
            f"{source} does not hold a theme",
            [f"the file is a JSON {_kind(document)}, not an object"],
        )

    version = document.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ThemeError(
            f"{source} does not say which schema it was written with",
            [f"schema_version: is {_shown(version)}, not a whole number"],
        )
    if version != SCHEMA_VERSION:
        raise ThemeError(
            f"{source} was not written by this build",
            [
                f"schema_version: is {version} and this build writes "
                f"{SCHEMA_VERSION}; a bundled theme ships with its build"
            ],
        )

    # In the document's own order, so a file with two problems in it reports
    # the first one a reader would meet rather than whichever check ran first.
    tokens = _strings(_object(document, "tokens", source), "tokens.", source)

    channels = document.get("channels", [])
    if not isinstance(channels, list):
        raise ThemeError(
            f"{source} is not a theme this build can use",
            [f"channels: is a JSON {_kind(channels)}, not an array"],
        )
    for index, value in enumerate(channels):
        if not isinstance(value, str):
            raise ThemeError(
                f"{source} is not a theme this build can use",
                [f"channels[{index}]: is a JSON {_kind(value)}, not a string"],
            )

    groups = {}
    for name, values in _object(document, "groups", source).items():
        if not isinstance(values, dict):
            raise ThemeError(
                f"{source} is not a theme this build can use",
                [f"groups.{name}: is a JSON {_kind(values)}, not an object"],
            )
        groups[name] = _strings(values, f"groups.{name}.", source)

    # Everything left is `Theme`'s to refuse, and it does.
    return Theme(
        name=document.get("name", ""),
        author=document.get("author", ""),
        tokens=tokens,
        channels=tuple(channels),
        groups=groups,
    )


@cache
def builtin() -> Theme:
    """The default palette, read once per process from its bundled file.

    `@cache`d for `_template()`'s reason - it is one small file and the
    answer never changes within a run - and with `icons.icon()`'s warning
    attached: **a test that swaps the resource underneath this has to call
    `builtin.cache_clear()`**, or it asserts against a theme read three tests
    ago.

    There is no fallback (D-79). An installation without this file is one
    that cannot paint anything, and a second palette kept in Python for a run
    that never happens would be a second definition of the default that
    nothing ever checks.
    """
    where = f"{_THEME_PACKAGE}/{_BUILTIN_FILE}"
    try:
        text = (
            resources.files(_THEME_PACKAGE)
            .joinpath(_BUILTIN_FILE)
            .read_text(encoding="utf-8")
        )
    except (OSError, ModuleNotFoundError) as missing:
        raise ThemeError(
            "the built-in theme is missing from this installation",
            [f"{where}: {missing}"],
        ) from missing
    return strict(text, source=where)


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #


def dumps(theme: Theme) -> str:
    """`theme` as the text of a `.3dimtheme` file.

    Keys are sorted and the file ends in a newline, which is `project_io`'s
    discipline and D-13's reason: a file whose key order depends on the order
    a dictionary happened to be built in produces a diff every time it is
    written, and a format meant to live in git should not.

    The cost is real and is paid here rather than hidden: sorting puts
    `surface.hover` above `surface.window`, so the written palette no longer
    reads deepest-to-lightest the way the table in docs/04-ui-spec.md does.
    The document keeps the human ordering; the file keeps the deterministic
    one.

    Every key is written, including an `author` nobody set. A writer that
    omitted empty values would make what comes out depend on what went in,
    and the first thing anyone does with this function is compare two of its
    results.
    """
    document = {
        "schema_version": SCHEMA_VERSION,
        "name": theme.name,
        "author": theme.author,
        "tokens": dict(theme.tokens),
        "channels": list(theme.channels),
        "groups": {name: dict(values) for name, values in theme.groups.items()},
    }
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def save(theme: Theme, path: str | os.PathLike[str]) -> None:
    """Write `theme` to `path` as a `.3dimtheme`.

    A plain write, where `project_io.save` goes through a temporary file. The
    asymmetry is deliberate: that one is protecting a project, where an
    interrupted save truncates work that cannot be retyped, and this one
    writes a cosmetic file the application never overwrites on a user's
    behalf. If M8 ever grows a theme editor that saves over somebody's file,
    it inherits the temporary-file rule along with the feature.
    """
    Path(path).write_text(dumps(theme), encoding="utf-8")


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #


def loads(
    text: str, *, source: Path | None = None, over: Theme = BUILTIN
) -> ThemeReport:
    """Parse `text` as a `.3dimtheme` and merge it over `over`.

    `over` is a parameter rather than `BUILTIN` written into six places
    because M9 phase 3 turns the built-in theme into a file loaded through
    this same path (D-47), and a reader that can only merge over the one
    theme it imports has nothing to load the built-in *as*.
    """
    reading = _Reading()

    try:
        document = json.loads(text)
    except json.JSONDecodeError as broken:
        reading.error(f"line {broken.lineno}, column {broken.colno}", broken.msg)
        return ThemeReport(over, source, reading.problems)

    if not isinstance(document, dict):
        reading.error(
            "", f"the file holds a JSON {_kind(document)}, not a theme object"
        )
        return ThemeReport(over, source, reading.problems)

    migrated = _versioned(reading, document)
    if migrated is None:
        return ThemeReport(over, source, reading.problems)

    tokens = _tokens(reading, migrated.get("tokens"), over)
    theme = Theme(
        name=_name(reading, migrated, source.stem if source else over.name),
        author=_author(reading, migrated),
        tokens=tokens,
        channels=_channels(reading, migrated.get("channels"), over),
        groups=_groups(reading, migrated.get("groups"), over, tokens),
    )

    # Advisory, and only ever advisory. 04-ui-spec.md, *Contrast is checked,
    # not enforced*: enforcing the rule would mean refusing somebody's own
    # theme on their own machine, which is not a call this application gets
    # to make. The built-in is the other audience and is held to it by test.
    for failing in theme.contrast_problems():
        reading.warn("contrast", failing)

    return ThemeReport(theme, source, reading.problems)


def load(path: str | os.PathLike[str], *, over: Theme = BUILTIN) -> ThemeReport:
    """Read a `.3dimtheme` from disk and merge it over `over`.

    A file that cannot be read is a reported problem rather than the
    `OSError` `project_io.load` lets through, and the difference is the same
    one the module docstring makes: a project the user asked to open and
    could not is a dead end they have to hear about, and a theme that is not
    there is a grey window and a line in the notice list.
    """
    source = Path(path)
    reading = _Reading()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as unreadable:
        reading.error(str(source), unreadable.strerror or "could not be read")
        return ThemeReport(over, source, reading.problems)
    except UnicodeDecodeError as undecodable:
        reading.error(
            f"{source}, byte {undecodable.start}",
            f"is not UTF-8 text: {undecodable.reason}",
        )
        return ThemeReport(over, source, reading.problems)
    return loads(text, source=source, over=over)
