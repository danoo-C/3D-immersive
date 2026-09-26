"""A SOFA file in, an `HrirSet` out - or the reason it could not be (05,
*The HRTF pipeline, 1. Load*).

What comes out is what every later stage of the pipeline reads and nothing
else: each measurement's direction as a unit vector **in the project's
axes**, both ears' responses at 48 kHz, the delays the file stores, and the
file's own licence and title. The axes are converted here and nowhere
else. SOFA's listener faces +x with +y to the left. The project's faces +Y
with +X to the right, and up is +Z in both (03). So SOFA's front is +Y, its
left is -X and its right +X.

**Levels are normalised** so that switching sets does not change how loud
the mix is: the mean per-ear energy is `EAR_ENERGY`, 0.25. That is S0's
target, a fixed 3 dB of headroom. At 0.5, SADIE II D1's loudest direction
peaked over full scale. The factor is kept on the set.

**Nothing here raises on input**, as with `core.io.media`: a set that will
not load is a `Refused` with a reason. Headless, and on a worker when it
runs in the application.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import sofar
import soxr

from immersive.assets.hrtf import SETS
from immersive.core.io.media import Refused, content_hash
from immersive.core.time import SAMPLE_RATE

#: The one convention this pipeline reads.
CONVENTION: Final = "SimpleFreeFieldHRIR"

#: The mean per-ear broadband energy a set is scaled to (S0 phase 1).
EAR_ENERGY: Final = 0.25

#: Two ears, and only two.
EARS: Final = 2


@dataclass(frozen=True, eq=False)
class HrirSet:
    """A set of head-related impulse responses, ready for phase 2."""

    #: As the file names itself, and its licence in its own words.
    title: str
    licence: str
    database: str
    #: `[M, 3]` unit vectors, project axes: X right, Y front, Z up.
    directions: npt.NDArray[np.float64]
    #: `[M, 2, N]` float32 at 48 kHz, left ear first, normalised.
    responses: npt.NDArray[np.float32]
    #: `[M, 2]` the delays the file stores, in samples at 48 kHz.
    delays: npt.NDArray[np.float64]
    #: The rate the set was measured at.
    source_rate: int
    #: The factor the responses were scaled by.
    gain: float
    #: The content hash of the file it came from: phase 4's cache key.
    hash: str

    @property
    def count(self) -> int:
        return int(self.responses.shape[0])

    @property
    def taps(self) -> int:
        return int(self.responses.shape[2])


def load(path: str | os.PathLike[str]) -> HrirSet | Refused:
    """The set in the SOFA file at `path`, or why it cannot be used."""
    source = Path(path)
    if not source.exists():
        return Refused(str(source), "is not there")
    if not source.is_file():
        return Refused(str(source), "is a folder, not a SOFA file")
    try:
        sofa = sofar.read_sofa(str(source), verify=False, verbose=False)
    except Exception as unreadable:  # sofar's own errors, and netCDF's
        return Refused(str(source), f"is not a SOFA file this can read ({unreadable})")
    return _from_sofa(sofa, source)


def builtin(set_id: str) -> HrirSet | Refused:
    """A built-in set by the id a project names it by (`HrtfRef.id`).

    Read through `importlib.resources` (D-30). Not yet fetched, it is
    refused with the command that fetches it.
    """
    entry = SETS.get(set_id)
    if entry is None:
        return Refused(set_id, "is not a built-in HRTF set")
    resource = resources.files("immersive.assets.hrtf").joinpath(entry.file)
    if not resource.is_file():
        return Refused(
            entry.title,
            "is not installed - `python3 launch.py --install` fetches it",
        )
    with resources.as_file(resource) as path:
        return load(path)


def _from_sofa(sofa: Any, source: Path) -> HrirSet | Refused:
    name = str(source)
    convention = str(sofa.GLOBAL_SOFAConventions)
    if convention != CONVENTION:
        return Refused(
            name,
            f"is a {convention} SOFA file; only {CONVENTION} sets can be used",
        )
    responses = np.asarray(sofa.Data_IR, dtype=np.float64)
    if responses.ndim != 3 or responses.shape[1] != EARS:
        return Refused(name, f"has responses shaped {responses.shape}, not two ears")
    count = responses.shape[0]
    rate = round(float(np.asarray(sofa.Data_SamplingRate).ravel()[0]))

    positions = np.asarray(sofa.SourcePosition, dtype=np.float64)
    positions = np.broadcast_to(positions, (count, 3))
    kind = str(sofa.SourcePosition_Type).lower()
    units = str(sofa.SourcePosition_Units).lower()
    directions = _directions(positions, kind, radians="rad" in units)

    delays = np.broadcast_to(
        np.asarray(sofa.Data_Delay, dtype=np.float64), (count, EARS)
    ) * (SAMPLE_RATE / rate)

    if rate != SAMPLE_RATE:
        responses = _resampled(responses, rate)
    energy = float(np.mean(np.sum(responses**2, axis=2)))
    if energy <= 0.0:
        return Refused(name, "holds no sound in any of its responses")
    gain = float(np.sqrt(EAR_ENERGY / energy))
    scaled = np.ascontiguousarray(responses * gain, dtype=np.float32)
    scaled.flags.writeable = False

    digest = content_hash(source)
    if isinstance(digest, Refused):
        return digest
    return HrirSet(
        title=str(getattr(sofa, "GLOBAL_Title", "")),
        licence=str(getattr(sofa, "GLOBAL_License", "")),
        database=str(getattr(sofa, "GLOBAL_DatabaseName", "")),
        directions=directions,
        responses=scaled,
        delays=np.ascontiguousarray(delays),
        source_rate=rate,
        gain=gain,
        hash=digest,
    )


def _directions(
    positions: npt.NDArray[np.float64], kind: str, *, radians: bool
) -> npt.NDArray[np.float64]:
    """SOFA source positions as unit vectors in the project's axes."""
    if kind == "cartesian":
        front, left, up = positions[:, 0], positions[:, 1], positions[:, 2]
    else:
        az = positions[:, 0] if radians else np.radians(positions[:, 0])
        el = positions[:, 1] if radians else np.radians(positions[:, 1])
        front = np.cos(el) * np.cos(az)
        left = np.cos(el) * np.sin(az)
        up = np.sin(el)
    vectors = np.stack([-left, front, up], axis=1)
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.ascontiguousarray(vectors / lengths)


def _resampled(
    responses: npt.NDArray[np.float64], rate: int
) -> npt.NDArray[np.float64]:
    """`[M, 2, N]` at `rate`, brought to 48 kHz along the taps."""
    count, ears, taps = responses.shape
    flat = responses.transpose(2, 0, 1).reshape(taps, count * ears)
    out = soxr.resample(flat, rate, SAMPLE_RATE)
    return np.ascontiguousarray(out.reshape(-1, count, ears).transpose(1, 2, 0))
