"""Audio files in; float32 at 48 kHz out - or the reason they could not be.

The project rate is fixed at 48 kHz (D-11), so every sample is brought to it
once, here, rather than converted on the way to the speakers. What comes back
is `(frames, channels)`: the shape `soundfile` reads and `sounddevice` plays,
so nothing between them has to transpose.

**Nothing in this module raises on input.** A sample that will not open is a
fact about the sample, and the importer has to turn a folder of them into one
report rather than stop at the first - the split M9 drew for theme files.
`soundfile` raises one exception type for everything from "not audio" to "not
there", and says *System error.* for the second, so this is the only place
that can say what actually went wrong.

A refusal carries a reason and no severity. `ui/notices.py` owns severities
and `core/` may not import `ui/` (N-5); the importer is the one that knows
this file was one of forty, and so what kind of trouble it is.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, overload

import numpy as np
import numpy.typing as npt
import soundfile
import soxr

from immersive.core.io.loudness import StemSpectra, measure
from immersive.core.model import MediaFile
from immersive.core.progress import Cancelled, Part
from immersive.core.time import SAMPLE_RATE

#: `soxr`'s high quality: 20-bit precision, which is -120 dB and below anything
#: a float32 mix shows. `VHQ` costs half as much again on every project load,
#: and N-4 has a budget.
QUALITY: Final = "HQ"

#: Mono or stereo (03, `MediaFile.channels`). More is refused rather than
#: guessed at (D-87).
MAX_CHANNELS: Final = 2

#: How much of a file is read at a time when hashing it: memory for one chunk,
#: never for the whole file.
CHUNK: Final = 1 << 20

#: How many frames `decode` reads at a time: each chunk moves the progress
#: and is where a cancel takes effect (F-59). 2^18 frames of 24-bit stereo is
#: 1.5 MB - a few milliseconds even from the Windows drive under WSL.
FRAMES_AT_ONCE: Final = 1 << 18

#: ⚠️ **MPEG audio is read in one call.** libsndfile 1.2.2 misdecodes an MP3
#: read in pieces: from the first boundary on, the frames after each one are
#: wrong - at 1 000 frames a read the whole file is noise, 0 dB against the
#: original where one read is 41 dB. WAV, AIFF, FLAC and OGG read in pieces
#: are exact. Found in M2 phase 8; `test_media.py` holds a canary that fails
#: when a libsndfile without the fault arrives, and then this can go.
WHOLE: Final = "MPEG"

#: How much of decoding is reading, when the file is resampled as well: from
#: M2 phase 8's measurement, reading 0.45 of a file and resampling 0.30.
READING: Final = 0.6

#: What a content hash starts with. The algorithm is part of the value, so a
#: later build that hashes differently can tell an old hash from a mismatch.
HASH_PREFIX: Final = "sha256:"

Audio = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Decoded:
    """A sample, at the project rate, and the rate it arrived at.

    `audio` is float32, `(frames, channels)`, C-contiguous and **read-only**:
    every clip that plays this sample shares the one array, and one that
    wrote to it would be editing all of them.

    `fold` is what a stereo sample loses folded to the average of its sides,
    as the factor that gives it back (D-129), and `spectra` its sides' own
    K-weighted spectra, by which a pair's loudness is read (D-133): both
    measured when it is decoded. Made any other way, `fold` is 1 and
    `spectra` is measured when it is first needed.
    """

    audio: Audio
    source_rate: int
    fold: float = 1.0
    spectra: StemSpectra | None = field(default=None, repr=False)

    @property
    def frames(self) -> int:
        return int(self.audio.shape[0])

    @property
    def channels(self) -> int:
        return int(self.audio.shape[1])

    def media_file(
        self, media_id: str, path: str | os.PathLike[str], hash: str = ""
    ) -> MediaFile:
        """The pool entry for this sample.

        `name` is the file's whole name, suffix included, as `03`'s example
        has it: `kick.wav` and `kick.mp3` are two samples and should look it.
        `hash` is `content_hash`'s, taken by the caller, which is the one
        that knows whether it already has one.
        """
        where = Path(path).absolute()
        return MediaFile(
            id=media_id,
            path=str(where),
            name=where.name,
            source_rate=self.source_rate,
            channels=self.channels,
            frames=self.frames,
            hash=hash,
        )


@dataclass(frozen=True)
class Refused:
    """Why a file is not a sample this application can use."""

    path: str
    reason: str

    def __str__(self) -> str:
        return f"{Path(self.path).name}: {self.reason}"


def frames_at_project_rate(frames: int, rate: int) -> int:
    """How many frames `frames` at `rate` become at 48 kHz.

    The exact ratio rounded half up - which is what `soxr` returns, measured
    across every rate and length tried before this was written. In integers,
    because a float product of two large counts can land a hair either side
    of a half and round the wrong way.
    """
    return (2 * frames * SAMPLE_RATE + rate) // (2 * rate)


@overload
def decode(
    path: str | os.PathLike[str], progress: None = None
) -> Decoded | Refused: ...


@overload
def decode(
    path: str | os.PathLike[str], progress: Part
) -> Decoded | Refused | Cancelled: ...


def decode(
    path: str | os.PathLike[str], progress: Part | None = None
) -> Decoded | Refused | Cancelled:
    """Read the file at `path` and bring it to the project rate.

    Read `FRAMES_AT_ONCE` frames at a time, moving `progress` through its
    stretch - reading, then resampling - and stopping between chunks if it
    is cancelled.
    """
    source = Path(path)
    if not source.exists():
        return Refused(str(source), "is not there")
    if not source.is_file():
        return Refused(str(source), "is a folder, not a sound file")

    read = _read(source, progress)
    if not isinstance(read, tuple):
        return read
    audio, rate = read
    if audio.shape[0] == 0:
        return Refused(str(source), "contains no audio")

    if rate != SAMPLE_RATE:
        if progress is not None:
            progress.at(READING)
            if progress.cancelled:
                return Cancelled(str(source))
        audio = soxr.resample(audio, rate, SAMPLE_RATE, quality=QUALITY)
    audio = np.ascontiguousarray(audio, dtype=np.float32)
    audio.flags.writeable = False
    spectra = measure(audio)
    if progress is not None:
        progress.at(1.0)
    folded = spectra.fold if audio.shape[1] == 2 else 1.0
    return Decoded(audio, int(rate), folded, spectra)


def _read(
    source: Path, progress: Part | None
) -> tuple[Audio, int] | Refused | Cancelled:
    """Every frame of `source`, as float32 at its own rate, a chunk at a time.

    Into an array sized by the frame count the file announces, trimmed to
    what was read if the file holds fewer. It cannot hold more that can be
    read: `soundfile` stops every read at the announced count, its one-shot
    `read` included.
    """
    try:
        with soundfile.SoundFile(source) as file:
            rate, channels, announced = file.samplerate, file.channels, file.frames
            if channels > MAX_CHANNELS:
                return Refused(
                    str(source),
                    f"has {channels} channels; only mono and stereo can be imported",
                )
            # Reading is the whole of decoding at the project rate, and
            # READING of it when resampling follows.
            share = 1.0 if rate == SAMPLE_RATE else READING
            if str(file.subtype).startswith(WHOLE):
                whole = file.read(dtype="float32", always_2d=True)
                if progress is not None:
                    progress.at(share)
                return whole, int(rate)
            audio = np.empty((max(announced, 0), channels), dtype=np.float32)
            at = 0
            while at < audio.shape[0]:
                if progress is not None and progress.cancelled:
                    return Cancelled(str(source))
                room = audio[at : at + FRAMES_AT_ONCE]
                got = file.read(dtype="float32", always_2d=True, out=room).shape[0]
                if got == 0:
                    break
                at += got
                if progress is not None and announced > 0:
                    progress.at(share * min(at / announced, 1.0))
    except (RuntimeError, OSError, ValueError) as unreadable:
        # LibsndfileError is a RuntimeError. Its message leads with "Error
        # opening '<the whole path>':", which the person already knows.
        return Refused(str(source), _reason(unreadable))
    return audio[:at], int(rate)


@overload
def content_hash(
    path: str | os.PathLike[str], progress: None = None
) -> str | Refused: ...


@overload
def content_hash(
    path: str | os.PathLike[str], progress: Part
) -> str | Refused | Cancelled: ...


def content_hash(
    path: str | os.PathLike[str], progress: Part | None = None
) -> str | Refused | Cancelled:
    """SHA-256 of the file's **bytes**, as `sha256:<hex>` (D-88).

    Bytes rather than decoded audio, because decoders differ by version and
    D-40 declines to promise the same floats on two machines - and a relink
    key and a cache key must mean the same file everywhere. A retagged file
    therefore hashes differently, which errs the safe way: it relinks with a
    notice, and its peaks are computed again.

    Read `CHUNK` bytes at a time, so a two-gigabyte WAV costs one chunk of
    memory to hash - each chunk moving `progress`, and a cancel taking effect
    before the next.
    """
    source = Path(path)
    if not source.exists():
        return Refused(str(source), "is not there")
    if not source.is_file():
        return Refused(str(source), "is a folder, not a sound file")

    digest = hashlib.sha256()
    try:
        size = source.stat().st_size
        read = 0
        with source.open("rb") as file:
            while True:
                if progress is not None and progress.cancelled:
                    return Cancelled(str(source))
                block = file.read(CHUNK)
                if not block:
                    break
                digest.update(block)
                read += len(block)
                if progress is not None and size > 0:
                    progress.at(min(read / size, 1.0))
    except OSError as unreadable:
        return Refused(str(source), f"could not be read ({unreadable.strerror})")
    if progress is not None:
        progress.at(1.0)
    return HASH_PREFIX + digest.hexdigest()


def _reason(error: Exception) -> str:
    said = getattr(error, "error_string", None) or str(error)
    return f"is not a sound file this can read ({said.strip().rstrip('.')})"
