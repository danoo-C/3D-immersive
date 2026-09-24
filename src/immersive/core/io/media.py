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

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
import soundfile
import soxr

from immersive.core.model import MediaFile
from immersive.core.time import SAMPLE_RATE

#: `soxr`'s high quality: 20-bit precision, which is -120 dB and below anything
#: a float32 mix shows. `VHQ` costs half as much again on every project load,
#: and N-4 has a budget.
QUALITY: Final = "HQ"

#: Mono or stereo (03, `MediaFile.channels`). More is refused rather than
#: guessed at (D-87).
MAX_CHANNELS: Final = 2

Audio = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Decoded:
    """A sample, at the project rate, and the rate it arrived at.

    `audio` is float32, `(frames, channels)`, C-contiguous and **read-only**:
    every clip that plays this sample shares the one array, and one that
    wrote to it would be editing all of them.
    """

    audio: Audio
    source_rate: int

    @property
    def frames(self) -> int:
        return int(self.audio.shape[0])

    @property
    def channels(self) -> int:
        return int(self.audio.shape[1])

    def media_file(self, media_id: str, path: str | os.PathLike[str]) -> MediaFile:
        """The pool entry for this sample, as far as decoding can fill it.

        `name` is the file's whole name, suffix included, as `03`'s example
        has it: `kick.wav` and `kick.mp3` are two samples and should look it.
        The hash is phase 3's.
        """
        where = Path(path).absolute()
        return MediaFile(
            id=media_id,
            path=str(where),
            name=where.name,
            source_rate=self.source_rate,
            channels=self.channels,
            frames=self.frames,
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


def decode(path: str | os.PathLike[str]) -> Decoded | Refused:
    """Read the file at `path` and bring it to the project rate."""
    source = Path(path)
    if not source.exists():
        return Refused(str(source), "is not there")
    if not source.is_file():
        return Refused(str(source), "is a folder, not a sound file")

    try:
        audio, rate = soundfile.read(source, dtype="float32", always_2d=True)
    except (RuntimeError, OSError, ValueError) as unreadable:
        # LibsndfileError is a RuntimeError. Its message leads with "Error
        # opening '<the whole path>':", which the person already knows.
        return Refused(str(source), _reason(unreadable))

    channels = int(audio.shape[1])
    if channels > MAX_CHANNELS:
        return Refused(
            str(source),
            f"has {channels} channels; only mono and stereo can be imported",
        )
    if audio.shape[0] == 0:
        return Refused(str(source), "contains no audio")

    if rate != SAMPLE_RATE:
        audio = soxr.resample(audio, rate, SAMPLE_RATE, quality=QUALITY)
    audio = np.ascontiguousarray(audio, dtype=np.float32)
    audio.flags.writeable = False
    return Decoded(audio, int(rate))


def _reason(error: Exception) -> str:
    said = getattr(error, "error_string", None) or str(error)
    return f"is not a sound file this can read ({said.strip().rstrip('.')})"
