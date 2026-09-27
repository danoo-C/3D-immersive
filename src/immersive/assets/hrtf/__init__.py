"""The built-in HRTF sets: where each comes from, and fetching it (QA-30).

**Fetched, not committed** (02, 08). A set is downloaded at install, checked
against the SHA-256 recorded here, and kept beside this module - gitignored,
and shipped in the wheel as a build artifact (`pyproject.toml`). Nothing in
the repository holds the data itself.

**Stdlib only.** `launch.py --install` loads this one file by path, before
the environment exists and without importing the package, so the registry
has one home and the launcher cannot drift from it. The application reads
the sets through `importlib.resources` (D-30), in `audio/hrtf/sofa.py`.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: How much is read, hashed and written at a time.
CHUNK = 1 << 20


@dataclass(frozen=True)
class Builtin:
    """One built-in set: what a project names it, and where it comes from."""

    #: What `HrtfRef.id` says - in every project, so never renamed.
    id: str
    #: Its file, as published.
    file: str
    url: str
    sha256: str
    #: Bytes, for what the install says it will download.
    size: int
    #: What the install calls it.
    title: str


#: The sets the application can name. SADIE II D1 is the spike's set and
#: QA-30's leading candidate: Apache 2.0 by its own `GLOBAL_License`, 8802
#: directions over the full sphere, 256 taps at 48 kHz. Its URL and digest
#: are the ones S0 fetched and heard.
SETS: dict[str, Builtin] = {
    "sadie-d1": Builtin(
        id="sadie-d1",
        file="D1_48K_24bit_256tap_FIR_SOFA.sofa",
        url="https://sofacoustics.org/data/database/sadie/D1_48K_24bit_256tap_FIR_SOFA.sofa",
        sha256="e6c72a84dd947b5ef75438ab96a9c2a32ed10f033472b9c4c11a49aff00a8a31",
        size=36_591_729,
        title="SADIE II D1",
    ),
}

#: Where the sets live in a checkout or an install: beside this module.
HERE = Path(__file__).resolve().parent


class FetchError(Exception):
    """A set that could not be fetched, in a sentence the install prints."""


def verified(entry: Builtin, into: Path = HERE) -> bool:
    """Whether `entry`'s file is in `into` and is the file it names."""
    target = into / entry.file
    if not target.is_file() or target.stat().st_size != entry.size:
        return False
    digest = hashlib.sha256()
    with target.open("rb") as file:
        while block := file.read(CHUNK):
            digest.update(block)
    return digest.hexdigest() == entry.sha256


def fetch(entry: Builtin, into: Path = HERE, url: str | None = None) -> Path:
    """Download `entry` into `into`, checked against its SHA-256.

    Written beside its final name and moved there only once its digest
    matches, so the loader never finds half a file, and a file that does not
    match is deleted. A set already there and matching is left alone. `url`
    stands in for the published one - a mirror, or a copy already on disk
    as a `file://` URL.
    """
    target = into / entry.file
    if verified(entry, into):
        return target
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    try:
        with (
            urllib.request.urlopen(url or entry.url, timeout=60) as response,
            partial.open("wb") as out,
        ):
            while block := response.read(CHUNK):
                digest.update(block)
                out.write(block)
    except (OSError, urllib.error.URLError) as failed:
        partial.unlink(missing_ok=True)
        raise FetchError(f"{entry.title} could not be downloaded ({failed})") from None
    if digest.hexdigest() != entry.sha256:
        partial.unlink(missing_ok=True)
        raise FetchError(
            f"{entry.title} did not match its checksum, so nothing was kept "
            "- run the install again"
        )
    partial.replace(target)
    return target
