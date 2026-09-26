"""What the engine convolves with (05, *4. Prepare the bank*; D-120).

A `Bank` is a set's minimum-phase responses, each zero-padded to `nfft` and
transformed once - `[M, 2, nfft/2 + 1]` complex64 - beside the signed ITDs,
the directions and their `Lookup`. `nfft` comes from the block and the
data, never a constant: `next_pow2(block + taps + ceil(max_itd) - 1)`. The
ITD is applied as a phase ramp, which is a circular delay, so the buffer has
to hold the response and the largest delay without wrapping.

**What is cached is what is slow** (D-120): the decomposition and the
direction index, 6.5 s for SADIE II D1 and the same at every block size,
keyed by the set's content hash in the one cache directory (D-59). The
transform is made from it on every load, 0.11 s at 512 frames; cached, it
would be 72 MB per block size ever tried. Written through a temporary file
and a rename, as the peaks are. A read that finds anything amiss - another
format, another set, a truncated file - is a miss, never an error.
"""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from immersive.audio.hrtf.decompose import Decomposed, decompose
from immersive.audio.hrtf.lookup import Lookup
from immersive.audio.hrtf.sofa import HrirSet
from immersive.core.io.media import Refused
from immersive.core.io.peaks import cache_directory
from immersive.core.progress import Cancelled, Part, Progress

#: The cache entry's layout. A different number is a miss, never a misread.
FORMAT: Final = 1

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
    #: `[M, 2, nfft/2 + 1]` complex64: each minimum-phase response's spectrum.
    filters: npt.NDArray[np.complex64]


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
    filters.flags.writeable = False
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
    )


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
