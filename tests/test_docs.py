"""The documentation invariants, enforced.

doc-system.md §7 lists six invariants that "must hold at every commit" and
notes that they were checked by hand. A checklist that depends on someone
remembering to run it is a checklist that eventually stops being run, and the
failure mode of this particular one is silent: a dangling `D-` reference or a
broken link reads perfectly well right up until someone follows it.

Two notes from §7 are implemented here because they are what make the checks
usable rather than noisy:

- Fenced code blocks and inline code spans are stripped before matching.
  Without that, every template and every quoted pattern in doc-system.md and
  09-workflow.md registers as a broken link or an undefined identifier.
- All four identifier prefixes are checked. An F/N/D-only pass once walked
  straight past a dangling question-archive reference, which is why that
  prefix is in the list too. (No literal identifier appears in this file, so
  that the tests below cannot flag themselves.)

These tests need no Qt and no audio device.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

CANON = sorted(DOCS.glob("[0-9][0-9]-*.md"))
ALL_DOCS = sorted(DOCS.rglob("*.md"))
PROSE_FILES = [*ALL_DOCS, REPO / "README.md", REPO / "THIRD-PARTY-NOTICES.md"]

FENCED = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`]*`")
IDENTIFIER = re.compile(r"\b(?:F|N|D|QA)-\d+\b")
LINK = re.compile(r"\]\((?!https?://|mailto:)([^)#]+?)(?:#[^)]*)?\)")


def prose(path: Path) -> str:
    """A document's text with code blocks and inline spans removed."""
    return INLINE.sub("", FENCED.sub("", path.read_text(encoding="utf-8")))


def _defined() -> Counter[str]:
    """Every identifier the canon *mints*, per doc-system.md §3."""
    requirements = (DOCS / "01-requirements.md").read_text(encoding="utf-8")
    archive = (DOCS / "07-qa-archive.md").read_text(encoding="utf-8")

    found: Counter[str] = Counter()
    # F- and N- are list items; D- is a decision-log row.
    found.update(re.findall(r"^- (F-\d+|N-\d+)\b", requirements, re.M))
    found.update(re.findall(r"^\| (D-\d+) \|", requirements, re.M))
    # QA- is either a section heading or a row in the en-bloc table.
    found.update(re.findall(r"^### (QA-\d+)\b", archive, re.M))
    found.update(re.findall(r"^\| (QA-\d+) \|", archive, re.M))
    return found


DEFINED = _defined()


def test_identifiers_are_defined_exactly_once() -> None:
    """doc-system.md §7: no identifier is defined twice."""
    duplicates = {name: count for name, count in DEFINED.items() if count > 1}
    assert not duplicates, f"defined more than once: {duplicates}"


def test_every_identifier_prefix_is_populated() -> None:
    """Guard against the detector passing vacuously if a regex stops matching."""
    for prefix in ("F-", "N-", "D-", "QA-"):
        assert any(k.startswith(prefix) for k in DEFINED), f"no {prefix} found"


@pytest.mark.parametrize("path", PROSE_FILES, ids=lambda p: str(p.name))
def test_every_cited_identifier_is_defined(path: Path) -> None:
    """doc-system.md §7: every F-, N-, D- and QA- cited anywhere is defined."""
    dangling = sorted(
        {name for name in IDENTIFIER.findall(prose(path)) if name not in DEFINED}
    )
    assert not dangling, f"{path.relative_to(REPO)} cites undefined: {dangling}"


def test_source_and_tests_cite_only_defined_identifiers() -> None:
    """The rule is worth as much in a docstring as in a document."""
    dangling: dict[str, list[str]] = {}
    for source in [
        *sorted((REPO / "src").rglob("*.py")),
        *sorted((REPO / "tests").rglob("*.py")),
        REPO / "pyproject.toml",
    ]:
        text = source.read_text(encoding="utf-8")
        missing = sorted(
            {name for name in IDENTIFIER.findall(text) if name not in DEFINED}
        )
        if missing:
            dangling[str(source.relative_to(REPO))] = missing
    assert not dangling, f"undefined identifiers cited in code: {dangling}"


def test_identifiers_are_contiguous() -> None:
    """Numbers only go up and are never reused, so a gap means one went missing.

    doc-system.md §3 allows retiring a decision but requires the row to stay,
    so a hole in the sequence is a deletion someone made by hand.
    """
    for prefix in ("F", "N", "D", "QA"):
        numbers = sorted(
            int(name.split("-")[1]) for name in DEFINED if name.startswith(f"{prefix}-")
        )
        expected = list(range(1, len(numbers) + 1))
        assert numbers == expected, f"{prefix}- sequence has holes: {numbers}"


def test_doc_system_high_water_marks_are_current() -> None:
    """doc-system.md §3 tabulates the highest identifier of each kind.

    It is exactly the sort of number §2 warns about: one home, cited
    elsewhere, and quietly wrong the moment the log grows.
    """
    table = (DOCS / "doc-system.md").read_text(encoding="utf-8")
    for prefix in ("F", "N", "D", "QA"):
        highest = max(
            int(name.split("-")[1]) for name in DEFINED if name.startswith(f"{prefix}-")
        )
        claimed = re.search(rf"\| `{prefix}-n` \|.*?\| ({prefix}-\d+) \|", table)
        assert claimed, f"no high-water row for {prefix}- in doc-system.md §3"
        assert claimed.group(1) == f"{prefix}-{highest}", (
            f"doc-system.md §3 claims {claimed.group(1)}, "
            f"but the highest defined is {prefix}-{highest}"
        )


@pytest.mark.parametrize("path", PROSE_FILES, ids=lambda p: str(p.name))
def test_relative_links_resolve(path: Path) -> None:
    """doc-system.md §7: every relative link resolves to a file that exists."""
    broken = [
        target
        for target in LINK.findall(prose(path))
        if not (path.parent / target).exists()
    ]
    assert not broken, f"{path.relative_to(REPO)} links to missing: {broken}"


def test_every_plan_has_a_phase_beside_it() -> None:
    """09-workflow.md: a plan mirrors its phase's filename exactly."""
    orphans = [
        str(plan.relative_to(REPO))
        for plan in sorted(DOCS.rglob("plans/*.md"))
        if not (plan.parent.parent / plan.name).exists()
    ]
    assert not orphans, f"plans with no matching phase: {orphans}"


def test_docs_readme_lists_every_numbered_document_and_no_others() -> None:
    """doc-system.md §7, and the reason 00-09 are discoverable at all."""
    readme = (DOCS / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"\((\d\d-[a-z-]+\.md)\)", readme))
    actual = {path.name for path in CANON}
    assert listed == actual, (
        f"missing from docs/README.md: {sorted(actual - listed)}; "
        f"listed but absent: {sorted(listed - actual)}"
    )


def test_third_party_notices_covers_every_runtime_dependency() -> None:
    """A bundle ships these; an attribution file written at release is late."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)^\]", pyproject, re.S | re.M)
    assert block, "no dependencies block in pyproject.toml"
    names = re.findall(r'^\s*"([A-Za-z0-9_.-]+)', block.group(1), re.M)
    assert names, "no dependencies parsed"

    notices = (REPO / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8").lower()
    missing = [name for name in names if name.lower() not in notices]
    assert not missing, f"not attributed in THIRD-PARTY-NOTICES.md: {missing}"


def test_the_licence_file_exists_and_is_declared() -> None:
    """pyproject.toml claimed MIT while no LICENSE file existed to ship."""
    assert (REPO / "LICENSE").is_file()
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "MIT"' in pyproject
    assert "LICENSE" in pyproject
