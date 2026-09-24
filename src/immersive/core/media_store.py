"""Samples prepared for the session, and the rules for admitting them.

Preparing one file is phases 2, 3 and 4 of M2 in one call - decode, hash,
peaks - and it runs on a worker, so nothing here touches Qt (N-5).

What was prepared is kept in a `MediaStore` by media id: the decoded audio
that audition and playback read, and the pyramid the pool draws. The store is
**not the model**. Nothing in it is saved, and it outlives the pool entries it
serves: undoing an import takes the entries out of the pool and leaves their
audio here, so Redo puts back what is already decoded instead of decoding it
again.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from immersive.core.io.media import Decoded, Refused, content_hash, decode
from immersive.core.io.peaks import Pyramid, peaks
from immersive.core.model import MEDIA_PREFIX, MediaFile, Project, all_ids, mint_id

#: What a folder import tries: F-5's formats by suffix, in any case (D-93).
#: Everything else in a sample folder - readmes, cover art - is passed over
#: without a word, so a report of what failed lists only real failures.
SUFFIXES: Final = frozenset(
    {".wav", ".wave", ".aif", ".aiff", ".aifc", ".flac", ".ogg", ".oga", ".mp3"}
)


def find_audio(folder: str | os.PathLike[str]) -> list[Path]:
    """Every file below `folder` that an import should try, sorted.

    Hidden files are passed over as well: macOS leaves a `._kick.wav` beside
    every `kick.wav` on any drive it has touched, and those are not audio.
    A folder that is not there, or cannot be read, holds nothing to try.
    """
    root = Path(folder)
    try:
        found = [
            path
            for path in root.rglob("*")
            if path.suffix.lower() in SUFFIXES
            and not any(part.startswith(".") for part in path.relative_to(root).parts)
            and path.is_file()
        ]
    except OSError:
        return []
    return sorted(found)


@dataclass(frozen=True)
class Prepared:
    """One file, decoded, hashed and summarised - ready to join the pool."""

    path: Path
    decoded: Decoded
    hash: str
    pyramid: Pyramid

    def media_file(self, media_id: str) -> MediaFile:
        return self.decoded.media_file(media_id, self.path, self.hash)


def prepare(
    path: str | os.PathLike[str], cache: Path | None = None
) -> Prepared | Refused:
    """Everything the session needs from one file, or why it cannot have it.

    Synchronous and headless: the importer runs it on a worker. Peaks come
    through the cache (F-9), so a sample imported before is summarised once.
    """
    decoded = decode(path)
    if isinstance(decoded, Refused):
        return decoded
    digest = content_hash(path)
    if isinstance(digest, Refused):
        return digest
    return Prepared(
        Path(path).absolute(), decoded, digest, peaks(digest, decoded.audio, cache)
    )


@dataclass
class MediaStore:
    """Decoded audio and peaks for the session, by media id."""

    _prepared: dict[str, Prepared] = field(default_factory=dict)

    def keep(self, media_id: str, prepared: Prepared) -> None:
        self._prepared[media_id] = prepared

    def audio(self, media_id: str) -> Decoded | None:
        kept = self._prepared.get(media_id)
        return kept.decoded if kept is not None else None

    def peaks(self, media_id: str) -> Pyramid | None:
        kept = self._prepared.get(media_id)
        return kept.pyramid if kept is not None else None

    def __contains__(self, media_id: object) -> bool:
        return media_id in self._prepared


@dataclass(frozen=True)
class Admission:
    """What one import adds, and what it does not and why."""

    #: New pool entries, each with what was prepared for it, in path order.
    admitted: list[tuple[MediaFile, Prepared]]
    #: Files that could not be prepared.
    refused: list[Refused]
    #: Files whose audio is already in the pool, or earlier in this import.
    already: list[Path]


def admit(project: Project, results: list[Prepared | Refused]) -> Admission:
    """Decide what an import adds to `project`'s pool (D-93).

    Audio already in the pool is not added again: two entries for one sample
    are two rows that are one thing, and a relink of one would leave the
    other stale. The same audio twice within one import counts the same way.
    Ids are minted here, fresh against the project and against each other.
    """
    known = {media.hash for media in project.media_pool if media.hash}
    taken = all_ids(project)
    admitted: list[tuple[MediaFile, Prepared]] = []
    refused: list[Refused] = []
    already: list[Path] = []
    for result in results:
        if isinstance(result, Refused):
            refused.append(result)
            continue
        if result.hash in known:
            already.append(result.path)
            continue
        media_id = mint_id(MEDIA_PREFIX, taken)
        taken.add(media_id)
        known.add(result.hash)
        admitted.append((result.media_file(media_id), result))
    return Admission(admitted, refused, already)
