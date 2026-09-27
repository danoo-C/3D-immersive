"""Pointing a sample that has gone at a file that is here (D-90).

The rules are headless and asserted here without a window; the last section
checks only what the window adds, which is the notices.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import soundfile

from immersive.app import build_application
from immersive.core.document import Document
from immersive.core.edits import Relink
from immersive.core.io import project_io
from immersive.core.io.media import Decoded, Refused, content_hash, decode
from immersive.core.model import Channel, Clip, MediaFile, Project
from immersive.core.relink import Relinked, relink
from immersive.core.time import SAMPLE_RATE
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity

SECOND = SAMPLE_RATE


def noise(seconds: float, seed: int) -> npt.NDArray[np.float32]:
    rng = np.random.default_rng(seed)
    return rng.uniform(-0.5, 0.5, round(SAMPLE_RATE * seconds)).astype(np.float32)


def sample(path: Path, audio: npt.NDArray[np.float32]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, audio, SAMPLE_RATE, subtype="FLOAT")
    return path


def entry(path: Path) -> MediaFile:
    decoded = decode(path)
    digest = content_hash(path)
    assert isinstance(decoded, Decoded) and isinstance(digest, str)
    return decoded.media_file("m-00000001", path, digest)


def opened(tmp_path: Path, media: MediaFile, *, clip_frames: int) -> Document:
    """A saved project whose one clip uses `clip_frames` of `media`, reopened
    - so `missing` is whatever the filesystem says, as it is for real."""
    channel = Channel("c-00000001", "A", "#A855F7")
    channel.clips = [Clip("k-00000001", media.id, 0, 0, clip_frames)]
    project_io.save(
        Project(media_pool=[media], channels=[channel]), tmp_path / "song.3dim"
    )
    document = Document()
    document.open(tmp_path / "song.3dim")
    return document


@pytest.fixture
def moved(tmp_path: Path) -> tuple[Document, Path]:
    """A project whose sample has been moved: missing where it was, and the
    same bytes somewhere else."""
    original = sample(tmp_path / "samples" / "kick.wav", noise(1.0, seed=1))
    document = opened(tmp_path, entry(original), clip_frames=SECOND // 2)
    elsewhere = tmp_path / "moved" / "kick.wav"
    elsewhere.parent.mkdir()
    original.rename(elsewhere)
    document.open(tmp_path / "song.3dim")  # reopen, now that it has gone
    assert document.project.media_pool[0].missing
    return document, elsewhere


def media_of(document: Document) -> MediaFile:
    return document.project.media_pool[0]


# --------------------------------------------------------------------------- #
# the rules
# --------------------------------------------------------------------------- #


def test_the_same_file_elsewhere_relinks_and_says_it_is_the_same(
    moved: tuple[Document, Path],
) -> None:
    document, elsewhere = moved

    result = relink(document, media_of(document), elsewhere)

    assert result == Relinked(same_audio=True)
    assert Path(media_of(document).path) == elsewhere
    assert not media_of(document).missing


def test_undoing_a_relink_says_the_sample_is_gone_again(
    moved: tuple[Document, Path],
) -> None:
    """Otherwise Undo claims the audio is back when it is not."""
    document, elsewhere = moved
    was = media_of(document).path
    relink(document, media_of(document), elsewhere)

    assert document.undo()
    assert media_of(document).path == was
    assert media_of(document).missing

    assert document.redo()
    assert Path(media_of(document).path) == elsewhere
    assert not media_of(document).missing


def test_different_audio_relinks_takes_its_facts_and_says_so(
    moved: tuple[Document, Path], tmp_path: Path
) -> None:
    """A re-export is the ordinary case. The pool must describe what it points
    at now, not what it pointed at before."""
    document, _ = moved
    stand_in = sample(tmp_path / "other" / "kick v2.wav", noise(2.0, seed=2))

    result = relink(document, media_of(document), stand_in)

    assert result == Relinked(same_audio=False)
    media = media_of(document)
    assert media.name == "kick v2.wav"
    assert media.frames == 2 * SECOND
    assert media.hash == content_hash(stand_in)
    assert media.id == "m-00000001", "the id is what every clip holds"


def test_a_file_too_short_for_the_clips_is_refused_and_changes_nothing(
    moved: tuple[Document, Path], tmp_path: Path
) -> None:
    document, _ = moved
    before = (media_of(document).path, media_of(document).frames)
    short = sample(tmp_path / "other" / "blip.wav", noise(0.1, seed=3))

    result = relink(document, media_of(document), short)

    assert isinstance(result, Refused)
    assert "cannot stand in for kick.wav" in result.reason
    assert "past the media's" in result.reason, "validate()'s own words"
    assert (media_of(document).path, media_of(document).frames) == before
    assert media_of(document).missing
    assert not document.can_undo


def test_a_file_that_is_not_audio_is_refused(
    moved: tuple[Document, Path], tmp_path: Path
) -> None:
    document, _ = moved
    fake = tmp_path / "fake.wav"
    fake.write_text("not audio", encoding="utf-8")

    assert isinstance(relink(document, media_of(document), fake), Refused)
    assert media_of(document).missing
    assert not document.can_undo


def test_an_old_project_cannot_compare_and_says_so(tmp_path: Path) -> None:
    """D-89: an empty hash is unknown, so the answer is neither yes nor no -
    and after relinking, the sample has one."""
    path = sample(tmp_path / "kick.wav", noise(1.0, seed=4))
    old = entry(path)
    old.hash = ""
    document = opened(tmp_path, old, clip_frames=SECOND // 2)

    result = relink(document, media_of(document), path)

    assert result == Relinked(same_audio=None)
    assert media_of(document).hash == content_hash(path)


def test_a_relink_clears_missing_whatever_it_is_handed() -> None:
    """The command's own promise, not its caller's.

    `relink()` always hands it a freshly decoded entry, which is never missing,
    so no test through `relink()` could tell whether `Relink` clears the mark
    or merely copies it. The sweep found that; a replacement built any other
    way - from another project's pool, say - must not carry `missing` in.
    """
    media = MediaFile("m-00000001", "/gone.wav", "gone.wav", SAMPLE_RATE, 1, 10)
    media.missing = True
    replacement = MediaFile("m-00000001", "/here.wav", "here.wav", SAMPLE_RATE, 1, 10)
    replacement.missing = True

    command = Relink(media, replacement)
    command.do()
    assert not media.missing

    command.undo()
    assert media.missing


# --------------------------------------------------------------------------- #
# the window's notices
# --------------------------------------------------------------------------- #


@pytest.fixture
def window() -> Iterator[MainWindow]:
    build_application([])
    made = MainWindow()
    yield made
    made.deleteLater()


def adopt(window: MainWindow, tmp_path: Path) -> None:
    """Open the moved project through the window."""
    assert window.open_project(tmp_path / "song.3dim")
    window.notices().clear()


@pytest.mark.gui
def test_the_same_audio_is_quiet(
    window: MainWindow, moved: tuple[Document, Path], tmp_path: Path
) -> None:
    _, elsewhere = moved
    adopt(window, tmp_path)

    assert window.relink_media(media_of(window.document()), elsewhere)
    assert window.notices().newest_first() == []


@pytest.mark.gui
def test_different_audio_is_one_warning(
    window: MainWindow, moved: tuple[Document, Path], tmp_path: Path
) -> None:
    adopt(window, tmp_path)
    stand_in = sample(tmp_path / "other" / "kick v2.wav", noise(2.0, seed=5))

    assert window.relink_media(media_of(window.document()), stand_in)

    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.WARN
    assert notice.message == "kick.wav now points at different audio"


@pytest.mark.gui
def test_a_refusal_is_one_error(
    window: MainWindow, moved: tuple[Document, Path], tmp_path: Path
) -> None:
    adopt(window, tmp_path)
    short = sample(tmp_path / "other" / "blip.wav", noise(0.1, seed=6))

    assert not window.relink_media(media_of(window.document()), short)

    [notice] = window.notices().newest_first()
    assert notice.severity is Severity.ERROR
    assert notice.message == "kick.wav was not relinked"
