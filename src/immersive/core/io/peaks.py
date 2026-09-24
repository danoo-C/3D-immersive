"""Waveform peaks: a min/max pyramid, and the cache that keeps it (F-9, D-59).

Level 0 summarises every `BUCKET` frames; each level above summarises `RATIO`
buckets of the one below, up to a level of one bucket that is the whole
file's minimum and maximum. A drawing reads the coarsest level that still has
a bucket or two per pixel: a 120-pixel thumbnail of five minutes of stereo
reads 55 buckets, not fourteen million frames.

Per channel and in float32. Float sources keep their overs (phase 2 of M2),
and a pyramid in a narrower integer type would clip exactly those.

These numbers are for drawing, not listening. Finer than `BUCKET` is M3's
problem at deep zoom, where it can read the audio itself.

**The cache never raises.** `03` calls the whole directory safe to delete, so
an entry that is missing, truncated, corrupt, from another format version or
for another length is a miss: the pyramid is built again and the entry
rewritten. A cache that could stop a project opening would be worse than no
cache.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

#: Frames per bucket at the finest level.
BUCKET: Final = 256

#: Buckets of one level per bucket of the level above.
RATIO: Final = 4

#: The on-disk format. An entry written by any other version is a miss.
FORMAT: Final = 1

#: What a cache key looks like: `content_hash`'s `algorithm:hex`. Checked,
#: because the key becomes a file name and must not be able to leave the
#: directory it is put in.
_KEY = re.compile(r"^([a-z0-9]+):([0-9a-f]+)$")

Audio = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Level:
    """One level: the lowest and highest sample in each bucket, per channel.

    `low` and `high` are `(buckets, channels)`. The last bucket covers
    whatever frames are left, which may be fewer than `bucket`.
    """

    bucket: int
    low: Audio
    high: Audio

    @property
    def buckets(self) -> int:
        return int(self.low.shape[0])


@dataclass(frozen=True)
class Pyramid:
    """Every level of one sample's peaks, finest first."""

    frames: int
    channels: int
    levels: tuple[Level, ...]


def build(audio: Audio) -> Pyramid:
    """Summarise `audio`, `(frames, channels)`, into a pyramid.

    Each level is built from the one below rather than from the audio, which
    is what makes the whole pyramid cost little more than its finest level -
    the min of four minima is the minimum of what they covered.
    """
    frames, channels = (int(size) for size in audio.shape)
    if frames == 0:
        raise ValueError("there are no peaks of nothing; decode refuses empty files")

    low, high = _reduce(audio, audio, BUCKET)
    levels = [Level(BUCKET, low, high)]
    while levels[-1].buckets > 1:
        below = levels[-1]
        low, high = _reduce(below.low, below.high, RATIO)
        levels.append(Level(below.bucket * RATIO, low, high))
    return Pyramid(frames, channels, tuple(levels))


def _reduce(low: Audio, high: Audio, group: int) -> tuple[Audio, Audio]:
    """Minimum of `low` and maximum of `high` over each run of `group` rows.

    The rows left over make one last, shorter group rather than being
    dropped - dropping them would draw the end of every sample as silence.

    Reduced channel-major, along contiguous memory. Reducing `(frames,
    channels)` across its strided middle axis took 0.7 s for five minutes of
    stereo; transposed first, the same reduction takes 0.07 s, and every
    imported sample pays it once.
    """
    rows, channels = (int(size) for size in low.shape)
    whole = rows // group
    lows: list[Audio] = []
    highs: list[Audio] = []
    if whole:
        cut = whole * group
        planar_low = np.ascontiguousarray(low[:cut].T).reshape(channels, whole, group)
        planar_high = (
            planar_low
            if high is low
            else np.ascontiguousarray(high[:cut].T).reshape(channels, whole, group)
        )
        lows.append(planar_low.min(axis=2).T)
        highs.append(planar_high.max(axis=2).T)
    if rows % group:
        lows.append(low[whole * group :].min(axis=0, keepdims=True))
        highs.append(high[whole * group :].max(axis=0, keepdims=True))
    return (
        np.ascontiguousarray(np.concatenate(lows), dtype=np.float32),
        np.ascontiguousarray(np.concatenate(highs), dtype=np.float32),
    )


# --------------------------------------------------------------------------- #
# the cache
# --------------------------------------------------------------------------- #


def cache_directory() -> Path:
    """The one user-level cache directory, per `03`'s table (D-59, D-91).

    Worked out here from the environment rather than asked of Qt: this module
    is in `core/`, which N-5 keeps free of Qt, and it runs on workers where
    nothing should be asking a `QApplication` anything. Reading the variables
    itself is also what lets the test suite redirect it on every platform.
    """
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "3dImmersive" / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "3dimmersive"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "3dimmersive"


def peaks(key: str, audio: Audio, directory: Path | None = None) -> Pyramid:
    """The pyramid for `audio`, from the cache when it is there.

    `key` is the sample's content hash - `MediaFile.hash`, or `content_hash`
    of the file when the model has none (D-89): the same value either way,
    and nothing written into the model. The same audio at two paths, or in
    two projects, is therefore one entry, which is F-9's "once per file".
    """
    entry = _entry(directory if directory is not None else cache_directory(), key)
    frames, channels = (int(size) for size in audio.shape)
    cached = _read(entry, frames, channels)
    if cached is not None:
        return cached
    pyramid = build(audio)
    _write(entry, pyramid)
    return pyramid


def _entry(directory: Path, key: str) -> Path:
    matched = _KEY.match(key)
    if matched is None:
        raise ValueError(f"{key!r} is not a content hash")
    algorithm, digest = matched.groups()
    return directory / "peaks" / f"{algorithm}-{digest}.npz"


def _read(entry: Path, frames: int, channels: int) -> Pyramid | None:
    """The entry at `entry` if it is a whole, current pyramid of this length."""
    try:
        with np.load(entry, allow_pickle=False) as stored:
            if (
                int(stored["format"]) != FORMAT
                or int(stored["frames"]) != frames
                or int(stored["channels"]) != channels
            ):
                return None
            levels: list[Level] = []
            bucket = BUCKET
            for index in range(int(stored["levels"])):
                low = np.asarray(stored[f"low{index}"], dtype=np.float32)
                high = np.asarray(stored[f"high{index}"], dtype=np.float32)
                expected = (-(-frames // bucket), channels)
                if low.shape != expected or high.shape != expected:
                    return None
                levels.append(Level(bucket, low, high))
                bucket *= RATIO
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        return None
    if not levels or levels[-1].buckets != 1:
        return None
    return Pyramid(frames, channels, tuple(levels))


def _write(entry: Path, pyramid: Pyramid) -> None:
    """Through a temporary file and a rename, as `project_io` writes.

    So an interrupted write leaves the old entry or none - never a truncated
    one a later read could take for real. A write that fails is not an
    error: the pyramid was built and is returned, and the next request builds
    it again.
    """
    # `Any` because numpy's stub for `savez` gives its keyword arguments an
    # `allow_pickle: bool` neighbour that a `**dict` of arrays cannot satisfy.
    arrays: dict[str, Any] = {
        "format": np.asarray(FORMAT, dtype=np.int64),
        "frames": np.asarray(pyramid.frames, dtype=np.int64),
        "channels": np.asarray(pyramid.channels, dtype=np.int64),
        "levels": np.asarray(len(pyramid.levels), dtype=np.int64),
    }
    for index, level in enumerate(pyramid.levels):
        arrays[f"low{index}"] = level.low
        arrays[f"high{index}"] = level.high

    temporary: str | None = None
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            dir=entry.parent, prefix=f".{entry.stem}.", suffix=".tmp"
        )
        with os.fdopen(handle, "wb") as file:
            np.savez(file, **arrays)
        Path(temporary).replace(entry)
        temporary = None
    except OSError:
        pass
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
