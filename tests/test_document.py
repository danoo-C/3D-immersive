"""The open project: what a document keeps, and what a failure must leave alone.

Headless, like everything in `core/` (N-5). The window's half of this phase is
in `test_project_in_the_window.py`; everything that can be settled without a
widget is settled here, where it costs milliseconds rather than a window.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from immersive.core.commands import InvalidEdit
from immersive.core.document import UNTITLED, Document
from immersive.core.edits import AddChannel, SetAttribute
from immersive.core.io import project_io
from immersive.core.model import Channel, MediaFile, Project
from immersive.core.time import SAMPLE_RATE


def a_channel(name: str = "A", channel_id: str = "c-00000001") -> Channel:
    return Channel(channel_id, name, "#A855F7")


def is_dirty(document: Document) -> bool:
    """Read through a call, for the reason `test_commands.py` gives.

    mypy narrows a property to a literal at its first assertion and then
    calls the opposite assertion unreachable, which is exactly wrong for a
    flag whose job is to change on the next line.
    """
    return document.is_dirty


def can_undo(document: Document) -> bool:
    return document.can_undo


def counted(document: Document) -> list[int]:
    """A list that grows by one every time the document says it changed."""
    calls: list[int] = []
    document.observe(lambda: calls.append(1))
    return calls


def saved_project(path: Path, *, channels: int = 1) -> Path:
    """A project file on disk, written by the real writer."""
    project = Project(
        channels=[a_channel(f"From disk {n}", f"c-0000010{n}") for n in range(channels)]
    )
    project_io.save(project, path)
    return path


# --------------------------------------------------------------------------- #
# a new document
# --------------------------------------------------------------------------- #


def test_a_new_document_is_clean_untitled_and_empty() -> None:
    document = Document()

    assert not is_dirty(document)
    assert not can_undo(document)
    assert document.path is None
    assert document.title == UNTITLED
    assert document.project == Project()


def test_an_edit_dirties_and_undoing_it_cleans() -> None:
    document = Document()

    document.push(AddChannel(document.project, a_channel()))
    assert is_dirty(document)
    assert can_undo(document)

    assert document.undo()
    assert not is_dirty(document)
    assert document.redo()
    assert is_dirty(document)


def test_a_refused_edit_changes_nothing_and_tells_nobody() -> None:
    document = Document()
    document.push(AddChannel(document.project, a_channel()))
    calls = counted(document)

    duplicate = a_channel("Same id")  # ids are unique (03, Rules)
    with pytest.raises(InvalidEdit):
        document.push(AddChannel(document.project, duplicate))

    assert [channel.name for channel in document.project.channels] == ["A"]
    assert calls == []


# --------------------------------------------------------------------------- #
# saving
# --------------------------------------------------------------------------- #


def test_an_untitled_document_cannot_be_saved_without_a_name() -> None:
    """Where it goes is the person's question; `save` does not guess."""
    with pytest.raises(ValueError):
        Document().save()


def test_save_as_writes_names_and_cleans(tmp_path: Path) -> None:
    document = Document()
    document.push(AddChannel(document.project, a_channel()))
    target = tmp_path / "mix.3dim"

    document.save_as(target)

    assert target.is_file()
    assert "c-00000001" in target.read_text(encoding="utf-8")
    assert document.path == target
    assert document.title == "mix"
    assert not is_dirty(document)


def test_the_next_save_goes_where_save_as_went(tmp_path: Path) -> None:
    document = Document()
    first, second = tmp_path / "first.3dim", tmp_path / "second.3dim"
    document.save_as(first)
    document.save_as(second)
    before = first.read_text(encoding="utf-8")

    document.push(AddChannel(document.project, a_channel()))
    document.save()

    assert first.read_text(encoding="utf-8") == before, "the old file moved"
    assert "c-00000001" in second.read_text(encoding="utf-8")


def test_a_save_as_that_fails_leaves_the_name_and_the_changes(tmp_path: Path) -> None:
    """A failed Save As must not aim the next Save at a file never written."""
    document = Document()
    document.save_as(tmp_path / "kept.3dim")
    document.push(AddChannel(document.project, a_channel()))

    with pytest.raises(OSError):
        document.save_as(tmp_path)  # a directory: the write cannot happen

    assert document.path == tmp_path / "kept.3dim"
    assert is_dirty(document)


def test_saving_elsewhere_keeps_media_reachable(tmp_path: Path) -> None:
    """D-71 end to end: absolute in memory, relative on disk, either way round."""
    audio = tmp_path / "samples" / "kick.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"not decoded before phase 2")
    document = Document()
    document.project.media_pool.append(
        MediaFile("m-00000001", str(audio), "kick", SAMPLE_RATE, 1, 100)
    )
    elsewhere = tmp_path / "projects" / "deep" / "mix.3dim"
    elsewhere.parent.mkdir(parents=True)

    document.save_as(elsewhere)
    reopened = Document()
    problems = reopened.open(elsewhere)

    assert problems == []
    assert Path(reopened.project.media_pool[0].path) == audio


# --------------------------------------------------------------------------- #
# opening
# --------------------------------------------------------------------------- #


def test_opening_replaces_the_project_and_starts_clean(tmp_path: Path) -> None:
    path = saved_project(tmp_path / "song.3dim")
    document = Document()
    document.push(AddChannel(document.project, a_channel()))

    problems = document.open(path)

    assert problems == []
    assert [channel.name for channel in document.project.channels] == ["From disk 0"]
    assert document.path == path
    assert document.title == "song"
    assert not is_dirty(document)


def test_undo_cannot_reach_into_the_previous_project(tmp_path: Path) -> None:
    """History belongs to one project. Keeping it would edit an invisible one."""
    path = saved_project(tmp_path / "song.3dim")
    document = Document()
    earlier = a_channel()
    document.push(AddChannel(document.project, earlier))
    previous = document.project

    document.open(path)

    assert not can_undo(document)
    assert not document.undo()
    assert previous.channels == [earlier], "the old project was touched"


@pytest.mark.parametrize(
    "contents",
    [b"{ this is not json", b"[]", b'{"schema_version": 1, "bpm": "fast"}'],
    ids=["broken", "not an object", "not a valid project"],
)
def test_a_file_that_is_not_a_project_changes_nothing(
    tmp_path: Path, contents: bytes
) -> None:
    """The open project, its history and its unsaved edits all survive."""
    bad = tmp_path / "bad.3dim"
    bad.write_bytes(contents)
    document = Document()
    document.save_as(tmp_path / "current.3dim")
    document.push(AddChannel(document.project, a_channel()))
    project, calls = document.project, counted(document)

    with pytest.raises(project_io.ProjectFileError):
        document.open(bad)

    assert document.project is project
    assert document.path == tmp_path / "current.3dim"
    assert is_dirty(document)
    assert can_undo(document)
    assert calls == []


def test_a_file_that_cannot_be_read_changes_nothing(tmp_path: Path) -> None:
    document = Document()
    document.push(AddChannel(document.project, a_channel()))
    project = document.project

    with pytest.raises(OSError):
        document.open(tmp_path / "not there.3dim")

    assert document.project is project
    assert document.path is None
    assert is_dirty(document)


def test_missing_media_opens_and_comes_back_as_problems(tmp_path: Path) -> None:
    """F-3: the arrangement survives its audio going missing."""
    audio = tmp_path / "gone.wav"
    audio.write_bytes(b"soon deleted")
    project = Project(
        media_pool=[MediaFile("m-00000001", str(audio), "gone", SAMPLE_RATE, 1, 100)]
    )
    path = tmp_path / "song.3dim"
    project_io.save(project, path)
    audio.unlink()

    document = Document()
    problems = document.open(path)

    assert len(problems) == 1
    assert document.project.media_pool[0].missing
    assert document.path == path


# --------------------------------------------------------------------------- #
# telling observers
# --------------------------------------------------------------------------- #


def test_every_change_is_told_once(tmp_path: Path) -> None:
    """Once, not at least once: a window that repaints twice per save is
    harmless today and a doubled engine snapshot at M3."""
    path = saved_project(tmp_path / "song.3dim")
    document = Document()
    calls = counted(document)

    document.push(AddChannel(document.project, a_channel()))
    document.undo()
    document.redo()
    document.save_as(tmp_path / "mine.3dim")
    document.push(SetAttribute(document.project.channels[0], "name", "Renamed"))
    document.save()
    document.open(path)
    document.new()

    assert len(calls) == 8


def test_an_undo_with_nothing_to_undo_tells_nobody() -> None:
    document = Document()
    calls = counted(document)

    assert not document.undo()
    assert not document.redo()
    assert calls == []


def test_new_forgets_the_file_and_the_history(tmp_path: Path) -> None:
    document = Document()
    document.save_as(tmp_path / "old.3dim")
    document.push(AddChannel(document.project, a_channel()))

    document.new()

    assert document.path is None
    assert document.title == UNTITLED
    assert not can_undo(document)
    assert not is_dirty(document)
    assert document.project == Project()
