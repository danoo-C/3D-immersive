"""Preparing samples and admitting them to the pool. Headless (N-5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile

from immersive.core.commands import UndoStack
from immersive.core.edits import AddMedia
from immersive.core.io.media import Refused
from immersive.core.media_store import (
    MediaStore,
    Prepared,
    admit,
    find_audio,
    prepare,
)
from immersive.core.model import MediaFile, Project, validate
from immersive.core.time import SAMPLE_RATE


def sample(path: Path, seed: int = 0, seconds: float = 0.25) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    audio = rng.uniform(-0.5, 0.5, round(SAMPLE_RATE * seconds)).astype(np.float32)
    soundfile.write(path, audio, SAMPLE_RATE, subtype="FLOAT")
    return path


def prepared(path: Path, cache: Path) -> Prepared:
    result = prepare(path, cache)
    assert isinstance(result, Prepared), result
    return result


# --------------------------------------------------------------------------- #
# what a folder import tries (D-93)
# --------------------------------------------------------------------------- #


def test_find_audio_recurses_and_sorts(tmp_path: Path) -> None:
    for name in ("drums/snare.wav", "drums/kick.wav", "pads/deep/warm.flac", "a.mp3"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x")

    found = [path.relative_to(tmp_path).as_posix() for path in find_audio(tmp_path)]

    assert found == [
        "a.mp3",
        "drums/kick.wav",
        "drums/snare.wav",
        "pads/deep/warm.flac",
    ]


def test_find_audio_keeps_f5s_suffixes_in_any_case_and_nothing_else(
    tmp_path: Path,
) -> None:
    keep = [
        "a.WAV",
        "b.Wave",
        "c.aif",
        "d.AIFF",
        "e.aifc",
        "f.flac",
        "g.ogg",
        "h.oga",
        "i.Mp3",
    ]
    ignore = ["readme.txt", "cover.jpg", "session.als", "notes", "j.wav.bak"]
    for name in keep + ignore:
        (tmp_path / name).write_bytes(b"x")

    assert sorted(path.name for path in find_audio(tmp_path)) == sorted(keep)


def test_find_audio_passes_over_hidden_files(tmp_path: Path) -> None:
    """macOS leaves `._kick.wav` beside every `kick.wav` it has touched."""
    (tmp_path / "kick.wav").write_bytes(b"x")
    (tmp_path / "._kick.wav").write_bytes(b"x")
    (tmp_path / ".trash").mkdir()
    (tmp_path / ".trash" / "old.wav").write_bytes(b"x")

    assert [path.name for path in find_audio(tmp_path)] == ["kick.wav"]


def test_find_audio_in_a_folder_that_is_not_there(tmp_path: Path) -> None:
    assert find_audio(tmp_path / "gone") == []


# --------------------------------------------------------------------------- #
# preparing, and keeping
# --------------------------------------------------------------------------- #


def test_prepare_fills_everything_the_pool_records(tmp_path: Path) -> None:
    path = sample(tmp_path / "kick.wav")

    result = prepared(path, tmp_path / "cache")
    entry = result.media_file("m-00000001")

    assert entry.name == "kick.wav"
    assert entry.hash.startswith("sha256:")
    assert entry.frames == result.decoded.frames == result.pyramid.frames
    assert validate(Project(media_pool=[entry])) == []


def test_prepare_refuses_what_decode_refuses(tmp_path: Path) -> None:
    fake = tmp_path / "fake.wav"
    fake.write_text("not audio", encoding="utf-8")

    assert isinstance(prepare(fake, tmp_path / "cache"), Refused)


def test_the_store_keeps_audio_and_peaks_by_id(tmp_path: Path) -> None:
    result = prepared(sample(tmp_path / "kick.wav"), tmp_path / "cache")
    store = MediaStore()

    store.keep("m-00000001", result)

    assert "m-00000001" in store
    assert store.audio("m-00000001") is result.decoded
    assert store.peaks("m-00000001") is result.pyramid
    assert store.audio("m-99999999") is None


# --------------------------------------------------------------------------- #
# admitting (D-93)
# --------------------------------------------------------------------------- #


def test_admit_mints_fresh_ids_and_keeps_path_order(tmp_path: Path) -> None:
    results: list[Prepared | Refused] = [
        prepared(sample(tmp_path / f"{n}.wav", seed=n), tmp_path / "cache")
        for n in range(3)
    ]
    project = Project(
        media_pool=[MediaFile("m-00000001", "/x.wav", "x.wav", SAMPLE_RATE, 1, 1)]
    )

    admission = admit(project, results)

    ids = [entry.id for entry, _ in admission.admitted]
    assert len(set(ids)) == 3 and "m-00000001" not in ids
    assert [entry.name for entry, _ in admission.admitted] == [
        "0.wav",
        "1.wav",
        "2.wav",
    ]


def test_admit_sets_aside_refusals(tmp_path: Path) -> None:
    fake = tmp_path / "fake.wav"
    fake.write_text("no", encoding="utf-8")
    good = prepared(sample(tmp_path / "good.wav"), tmp_path / "cache")

    admission = admit(Project(), [prepare(fake), good])

    assert [entry.name for entry, _ in admission.admitted] == ["good.wav"]
    assert len(admission.refused) == 1


def test_audio_already_in_the_pool_is_not_added_again(tmp_path: Path) -> None:
    """Under another name too: the hash decides, not the file name."""
    original = prepared(sample(tmp_path / "kick.wav", seed=1), tmp_path / "cache")
    copy = tmp_path / "elsewhere" / "kick copy.wav"
    copy.parent.mkdir()
    copy.write_bytes((tmp_path / "kick.wav").read_bytes())
    project = Project(media_pool=[original.media_file("m-00000001")])

    admission = admit(project, [prepared(copy, tmp_path / "cache")])

    assert admission.admitted == []
    assert admission.already == [copy.absolute()]


def test_the_same_audio_twice_in_one_import_is_added_once(tmp_path: Path) -> None:
    first = prepared(sample(tmp_path / "a.wav", seed=2), tmp_path / "cache")
    (tmp_path / "b.wav").write_bytes((tmp_path / "a.wav").read_bytes())
    second = prepared(tmp_path / "b.wav", tmp_path / "cache")

    admission = admit(Project(), [first, second])

    assert [entry.name for entry, _ in admission.admitted] == ["a.wav"]
    assert admission.already == [second.path]


# --------------------------------------------------------------------------- #
# one import, one undo
# --------------------------------------------------------------------------- #


def test_adding_several_samples_is_one_undo(tmp_path: Path) -> None:
    entries = [
        MediaFile(f"m-0000000{n}", f"/{n}.wav", f"{n}.wav", SAMPLE_RATE, 1, 10)
        for n in range(1, 5)
    ]
    project = Project()
    stack = UndoStack(project)

    stack.push(AddMedia(project, entries))
    assert project.media_pool == entries

    assert stack.undo()
    assert project.media_pool == []
    assert not stack.can_undo


def test_redo_puts_back_the_same_objects() -> None:
    """So anything holding them by id - the session's audio - still finds them."""
    entry = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10)
    project = Project()
    stack = UndoStack(project)
    stack.push(AddMedia(project, [entry]))
    stack.undo()

    stack.redo()

    assert project.media_pool[0] is entry


def test_adding_goes_after_what_is_there() -> None:
    first = MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10)
    later = MediaFile("m-00000002", "/b.wav", "b.wav", SAMPLE_RATE, 1, 10)
    project = Project(media_pool=[first])

    AddMedia(project, [later]).do()

    assert project.media_pool == [first, later]


@pytest.mark.parametrize("count", [0, 1])
def test_an_empty_or_single_addition_undoes_cleanly(count: int) -> None:
    entries = [MediaFile("m-00000001", "/a.wav", "a.wav", SAMPLE_RATE, 1, 10)][:count]
    project = Project()
    command = AddMedia(project, entries)
    command.do()
    command.undo()

    assert project.media_pool == []
