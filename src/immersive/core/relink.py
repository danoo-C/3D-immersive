"""Pointing a sample that has gone at a file that is here (F-3, D-90).

It reads through `io/media.py` and edits through `document.py`, and belongs to
neither, so it has a module of its own. M8's relink dialog is the caller in
waiting; this is everything that dialog will need except the dialog.

Headless, so every rule is asserted without a window, and synchronous, so
whoever calls it decides which thread reading a whole file happens on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from immersive.core.commands import InvalidEdit
from immersive.core.document import Document
from immersive.core.edits import Relink
from immersive.core.io.media import Refused, content_hash, decode
from immersive.core.model import MediaFile


@dataclass(frozen=True)
class Relinked:
    """A relink that happened, and whether it brought back the same audio.

    `same_audio` is `None` when there was nothing to compare against: a
    project saved before hashing existed keeps an empty hash (D-89), and
    claiming either answer about it would be a guess.
    """

    same_audio: bool | None


def relink(
    document: Document, media: MediaFile, path: str | os.PathLike[str]
) -> Relinked | Refused:
    """Point `media` at the file at `path`, as one undoable edit.

    A file that is not the same audio is allowed - a re-export with a fade
    fixed is the ordinary reason - and the result says so for the caller to
    report. A file too short for the clips that use it is refused, because
    `validate()` refuses the edit, and nothing changes.
    """
    decoded = decode(path)
    if isinstance(decoded, Refused):
        return decoded
    digest = content_hash(path)
    if isinstance(digest, Refused):
        return digest

    before = media.hash
    try:
        document.push(Relink(media, decoded.media_file(media.id, path, digest)))
    except InvalidEdit as broken:
        return Refused(
            os.fspath(path),
            "cannot stand in for "
            f"{media.name}: " + "; ".join(str(problem) for problem in broken.problems),
        )
    return Relinked(same_audio=None if not before else before == digest)
