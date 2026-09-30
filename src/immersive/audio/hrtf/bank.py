"""What the engine convolves with (05, *4. Prepare the bank*; D-120).

A `Bank` is a set's minimum-phase responses, each zero-padded to `nfft` and
transformed once - `[M, 2, nfft/2 + 1]` complex64 - beside the signed ITDs,
the directions and their `Lookup`. `nfft` comes from the block and the
data, never a constant: `next_pow2(block + taps + ceil(max_itd) - 1)`. The
ITD is applied as a phase ramp, which is a circular delay, so the buffer has
to hold the response and the largest delay without wrapping.

**Calibrated to flat** (D-128). After the transform, each direction's
loudness to pink noise is read from its spectra, and every filter is scaled
so the direction straight ahead is as loud as a response of 1 to both ears:
as loud as the sound played flat. Each direction's gain to the front's
loudness is kept as `evening`, for a project that wants every direction as
loud (D-131). Neither is cached: they are the transform's, and quick.

**What is cached is what is slow** (D-120): the decomposition and the
direction index, 6.5 s for SADIE II D1 and the same at every block size,
keyed by the set's content hash in the one cache directory (D-59). The
transform is made from it on every load, 0.11 s at 512 frames; cached, it
would be 72 MB per block size ever tried. Written through a temporary file
and a rename, as the peaks are. A read that finds anything amiss - another
format, another set, a truncated file - is a miss, never an error.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from immersive.audio.hrtf.decompose import Decomposed, decompose
from immersive.audio.hrtf.lookup import Lookup
from immersive.audio.hrtf.sofa import HrirSet
from immersive.core.io.loudness import pink_power, pink_weights
from immersive.core.io.media import Refused
from immersive.core.io.peaks import cache_directory
from immersive.core.progress import Cancelled, Part, Progress

#: The cache entry's layout. A different number is a miss, never a misread.
#: 2: the direction index's resolution is stored with it.
FORMAT: Final = 2

#: Straight ahead, in the project's axes (03): what the set is calibrated at.
AHEAD: Final = (0.0, 1.0, 0.0)

#: How many directions' spectra are measured at a time: bounded memory.
MEASURED_AT_ONCE: Final = 512

#: How much of preparing is decomposing, and how much indexing directions.
DECOMPOSED: Final = 0.8
INDEXED: Final = 0.98

_KEY = re.compile(r"^([a-z0-9]+):([0-9a-f]+)$")


@dataclass(frozen=True, eq=False)
class Bank:
    """One set, ready for the engine at one block size."""

    title: str
    #: The set's content hash: its cache key.
    hash: str
    block: int
    nfft: int
    taps: int
    #: The largest ITD's size, in samples; `nfft` holds it without wrapping.
    max_itd: float
    #: `[M, 3]` unit vectors, project axes, and their index.
    directions: npt.NDArray[np.float64]
    lookup: Lookup
    #: `[M]` signed, positive when the left ear is far (phase 2).
    itd: npt.NDArray[np.float64]
    #: `[M, 2, nfft/2 + 1]` complex64: each minimum-phase response's spectrum,
    #: calibrated to flat straight ahead (D-128).
    filters: npt.NDArray[np.complex64]
    #: The gain the calibration applied, in dB.
    calibration: float = 0.0
    #: `[M]` the gain that makes each direction as loud as straight ahead
    #: (D-131): 1 there, and whatever the head made elsewhere.
    evening: npt.NDArray[np.float64] = field(
        default_factory=lambda: np.ones(0, dtype=np.float64), repr=False
    )


def fft_size(block: int, taps: int, max_itd: float) -> int:
    """`next_pow2(block + taps + ceil(max_itd) - 1)`: room for a block
    convolved with a response delayed by the largest ITD, unwrapped."""
    needed = block + taps + int(np.ceil(max_itd)) - 1
    return 1 << (needed - 1).bit_length()


def prepare(
    hrirs: HrirSet,
    block: int,
    cache: Path | None = None,
    progress: Part | None = None,
) -> Bank | Refused | Cancelled:
    """The bank for `hrirs` at `block`: its decomposition and index from the
    cache if they are there, made and cached if not, then transformed."""
    moving = progress if progress is not None else Progress().part(0.0, 1.0)
    entry = _entry(cache if cache is not None else cache_directory(), hrirs.hash)
    stored = _read(entry, hrirs)
    if stored is None:
        decomposed = decompose(hrirs, moving.part(0.0, DECOMPOSED))
        if not isinstance(decomposed, Decomposed):
            return decomposed
        lookup = Lookup.build(hrirs.directions, moving.part(DECOMPOSED, INDEXED))
        if lookup is None:
            return Cancelled(hrirs.title)
        _write(
            entry, hrirs, decomposed.minimum, decomposed.itd, decomposed.max_itd, lookup
        )
        stored = (decomposed.minimum, decomposed.itd, decomposed.max_itd, lookup)
    minimum, itd, max_itd, lookup = stored
    taps = int(minimum.shape[-1])
    nfft = fft_size(block, taps, max_itd)
    filters = np.fft.rfft(minimum, n=nfft, axis=-1).astype(np.complex64)
    scale, evening = calibrated(filters, lookup, nfft)
    np.multiply(filters, np.complex64(scale), out=filters)
    filters.flags.writeable = False
    evening.flags.writeable = False
    moving.at(1.0)
    return Bank(
        title=hrirs.title,
        hash=hrirs.hash,
        block=block,
        nfft=nfft,
        taps=taps,
        max_itd=max_itd,
        directions=hrirs.directions,
        lookup=lookup,
        itd=itd,
        filters=filters,
        calibration=20.0 * math.log10(scale),
        evening=evening,
    )


def calibrated(
    filters: npt.NDArray[np.complex64], lookup: Lookup, nfft: int
) -> tuple[float, npt.NDArray[np.float64]]:
    """The factor that makes straight ahead as loud to pink noise as a flat
    response to both ears (D-128), and each direction's gain to that
    loudness (D-131). Straight ahead is the blend the engine plays there,
    which is one measurement when the set has one, as SADIE II D1 does. Both
    ears are summed, as BS.1770 sums channels, so a head's lean to one side
    stays."""
    weights = pink_weights(nfft)
    loudness = np.empty(filters.shape[0], dtype=np.float64)
    for start in range(0, filters.shape[0], MEASURED_AT_ONCE):
        part = filters[start : start + MEASURED_AT_ONCE]
        loudness[start : start + part.shape[0]] = pink_power(part, weights).sum(axis=1)
    vertices = np.zeros((1, 3), dtype=np.int64)
    blend = np.zeros((1, 3), dtype=np.float64)
    lookup.weigh(np.array([AHEAD], dtype=np.float64), vertices, blend)
    ahead = sum(
        float(blend[0, corner])
        * filters[int(vertices[0, corner])].astype(np.complex128)
        for corner in range(3)
    )
    front = float(pink_power(np.asarray(ahead), weights).sum())
    scale = math.sqrt(2.0 * float(weights.sum()) / front)
    evening = np.sqrt(front / np.where(loudness > 0.0, loudness, front))
    return scale, evening


# --------------------------------------------------------------------------- #
# the cache
# --------------------------------------------------------------------------- #

_Stored = tuple[npt.NDArray[np.float32], npt.NDArray[np.float64], float, Lookup]


def _entry(directory: Path, key: str) -> Path:
    matched = _KEY.match(key)
    if matched is None:
        raise ValueError(f"{key!r} is not a content hash")
    algorithm, digest = matched.groups()
    return directory / "hrtf" / f"{algorithm}-{digest}.npz"


def _read(entry: Path, hrirs: HrirSet) -> _Stored | None:
    """The entry if it is whole, current, and this set's."""
    try:
        with np.load(entry, allow_pickle=False) as stored:
            if (
                int(stored["format"]) != FORMAT
                or str(stored["hash"]) != hrirs.hash
                or int(stored["count"]) != hrirs.count
            ):
                return None
            minimum = np.asarray(stored["minimum"], dtype=np.float32)
            itd = np.asarray(stored["itd"], dtype=np.float64)
            faces = np.asarray(stored["faces"], dtype=np.int64)
            lookup = Lookup.assemble(
                faces,
                np.asarray(stored["inverses"], dtype=np.float64),
                np.asarray(stored["neighbours"], dtype=np.int64),
                np.asarray(stored["cells"], dtype=np.int64),
                np.asarray(stored["offsets"], dtype=np.int64),
                int(stored["resolution"]),
            )
            max_itd = float(stored["max_itd"])
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        return None
    if minimum.shape != (hrirs.count, 2, hrirs.taps) or itd.shape != (hrirs.count,):
        return None
    minimum.flags.writeable = False
    return minimum, itd, max_itd, lookup


def _write(
    entry: Path,
    hrirs: HrirSet,
    minimum: npt.NDArray[np.float32],
    itd: npt.NDArray[np.float64],
    max_itd: float,
    lookup: Lookup,
) -> None:
    """Through a temporary file and a rename, so an interrupted write leaves
    the old entry or none. A write that fails is not an error: the bank is
    still made, and the next load decomposes again."""
    arrays: dict[str, Any] = {
        "format": np.asarray(FORMAT, dtype=np.int64),
        "hash": np.asarray(hrirs.hash),
        "count": np.asarray(hrirs.count, dtype=np.int64),
        "minimum": minimum,
        "itd": itd,
        "max_itd": np.asarray(max_itd),
        "faces": lookup.faces,
        "inverses": lookup.inverses,
        "neighbours": lookup.neighbours,
        "cells": lookup.cells,
        "offsets": lookup.offsets,
        "resolution": np.asarray(lookup.resolution, dtype=np.int64),
    }
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
