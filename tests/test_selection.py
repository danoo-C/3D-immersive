"""The selection: one kind at a time, by identity, owned by the document
(D-57, D-96). No window, no Qt."""

from __future__ import annotations

from pathlib import Path

from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddClip, AddMedia, RemoveClip
from immersive.core.model import Channel, Clip, MediaFile, Project
from immersive.core.selection import Kind, Selection
from immersive.core.time import SAMPLE_RATE

MEDIA = MediaFile("m-00000001", "a.wav", "a.wav", SAMPLE_RATE, 1, 1_000_000)


def a_clip(identifier: str = "k-00000001", start: int = 0) -> Clip:
    return Clip(identifier, MEDIA.id, start, 0, 10_000)


def a_channel(identifier: str = "c-00000001", *clips: Clip) -> Channel:
    return Channel(identifier, "A", "#A855F7", clips=list(clips))


def told(selection: Selection) -> list[int]:
    calls: list[int] = []
    selection.observe(lambda: calls.append(1))
    return calls


# --------------------------------------------------------------------------- #
# one kind, by identity
# --------------------------------------------------------------------------- #


def test_a_selection_holds_one_kind() -> None:
    selection = Selection()
    clip, channel = a_clip(), a_channel()

    selection.select(Kind.CLIPS, [clip])
    selection.add(Kind.CHANNELS, [channel])

    assert selection.kind is Kind.CHANNELS
    assert selection.things() == [channel]
    assert clip not in selection


def test_toggling_a_thing_of_another_kind_selects_it_alone() -> None:
    selection = Selection()
    selection.select(Kind.CLIPS, [a_clip()])
    channel = a_channel()

    selection.toggle(Kind.CHANNELS, channel)

    assert selection.things() == [channel]


def test_membership_is_by_identity_not_equality() -> None:
    first, second = a_clip(), a_clip()
    assert first == second and first is not second
    selection = Selection()

    selection.select(Kind.CLIPS, [first])

    assert first in selection
    assert second not in selection
    selection.toggle(Kind.CLIPS, second)
    assert len(selection) == 2


def test_add_toggle_and_clear() -> None:
    a, b, c = a_clip("k-00000001"), a_clip("k-00000002"), a_clip("k-00000003")
    selection = Selection()

    selection.select(Kind.CLIPS, [a])
    selection.add(Kind.CLIPS, [b, c])
    assert selection.clips() == [a, b, c]
    selection.toggle(Kind.CLIPS, b)
    assert selection.clips() == [a, c]
    selection.clear()
    assert selection.kind is None and selection.things() == []


def test_an_empty_selection_has_no_kind() -> None:
    selection = Selection()
    selection.select(Kind.CLIPS, [])
    assert selection.kind is None


def test_every_change_is_told_once_and_no_change_tells_nobody() -> None:
    selection = Selection()
    calls = told(selection)
    clip = a_clip()

    selection.select(Kind.CLIPS, [clip])
    selection.select(Kind.CLIPS, [clip])
    selection.add(Kind.CLIPS, [clip])
    selection.clear()
    selection.clear()

    assert calls == [1, 1]


# --------------------------------------------------------------------------- #
# owned by the document
# --------------------------------------------------------------------------- #


def a_document() -> tuple[Document, Channel]:
    document = Document()
    document.push(AddMedia(document.project, [MEDIA]))
    channel = a_channel()
    document.push(AddChannel(document.project, channel))
    return document, channel


def test_an_undo_that_takes_a_selected_clip_away_takes_it_from_the_selection() -> None:
    document, channel = a_document()
    kept, going = a_clip("k-00000001"), a_clip("k-00000002", start=50_000)
    document.push(AddClip(channel, kept))
    document.push(AddClip(channel, going))
    document.selection.select(Kind.CLIPS, [kept, going])

    document.undo()

    assert document.selection.clips() == [kept]


def test_the_selection_is_pruned_before_anyone_is_told() -> None:
    """A widget reading the selection during the change it is told of must
    not find the clip the change took away."""
    document, channel = a_document()
    clip = a_clip()
    document.push(AddClip(channel, clip))
    document.selection.select(Kind.CLIPS, [clip])
    seen: list[list[Clip]] = []
    document.observe(lambda: seen.append(document.selection.clips()))

    document.push(RemoveClip(channel, clip))

    assert seen == [[]]


def test_new_and_open_clear_the_selection(tmp_path: Path) -> None:
    document, channel = a_document()
    document.selection.select(Kind.CHANNELS, [channel])
    document.save_as(tmp_path / "a.3dim")

    document.new()
    assert document.selection.kind is None

    document.selection.select(Kind.MEDIA, document.project.media_pool)
    document.open(tmp_path / "a.3dim")
    assert document.selection.kind is None


def test_a_reopened_projects_equal_things_are_not_selected(tmp_path: Path) -> None:
    """Pruned by identity: the reopened channel is equal, not the same."""
    document, channel = a_document()
    document.save_as(tmp_path / "a.3dim")
    document.selection.select(Kind.CHANNELS, [channel])

    document.open(tmp_path / "a.3dim")

    assert document.project.channels[0] == channel
    assert document.selection.things() == []


def test_pruning_keeps_the_selection_as_it_was_when_nothing_went() -> None:
    project = Project(channels=[a_channel("c-00000001"), a_channel("c-00000002")])
    selection = Selection()
    selection.select(Kind.CHANNELS, project.channels)
    calls = told(selection)

    selection.prune(project)

    assert selection.channels() == project.channels
    assert calls == []
