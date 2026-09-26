"""The built-in HRTF sets' registry and fetch (QA-30): fetched, checked by
SHA-256, never committed. Headless, and offline: every download here is a
`file://` URL on a temporary file."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from immersive.assets import hrtf
from immersive.assets.hrtf import Builtin, FetchError, fetch, verified

ROOT = Path(__file__).resolve().parent.parent


def published(tmp_path: Path, content: bytes = b"a set of responses" * 1000) -> Builtin:
    """A 'published' set: a file somewhere, and its entry naming it."""
    source = tmp_path / "published" / "set.sofa"
    source.parent.mkdir()
    source.write_bytes(content)
    return Builtin(
        id="test-set",
        file="set.sofa",
        url=source.as_uri(),
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        title="Test set",
    )


def test_a_matching_download_lands_and_is_verified(tmp_path: Path) -> None:
    entry = published(tmp_path)
    into = tmp_path / "assets"
    into.mkdir()

    landed = fetch(entry, into)

    assert landed == into / "set.sofa" and verified(entry, into)
    assert list(into.iterdir()) == [landed], "nothing else left behind"


def test_a_set_already_here_is_not_fetched_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = published(tmp_path)
    into = tmp_path / "assets"
    into.mkdir()
    fetch(entry, into)

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("fetched again")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    assert fetch(entry, into) == into / "set.sofa"


def test_a_download_that_does_not_match_leaves_nothing(tmp_path: Path) -> None:
    entry = published(tmp_path)
    wrong = Builtin(**{**entry.__dict__, "sha256": "0" * 64})
    into = tmp_path / "assets"
    into.mkdir()

    with pytest.raises(FetchError, match="checksum"):
        fetch(wrong, into)

    assert list(into.iterdir()) == []
    assert not verified(wrong, into)


def test_an_interrupted_download_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = published(tmp_path)
    into = tmp_path / "assets"
    into.mkdir()

    class Dropped:
        def __init__(self) -> None:
            self.reads = 0

        def __enter__(self) -> Dropped:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            self.reads += 1
            if self.reads > 1:
                raise OSError("connection reset")
            return b"half of it"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Dropped())

    with pytest.raises(FetchError, match="could not be downloaded"):
        fetch(entry, into)
    assert list(into.iterdir()) == []


def test_a_file_of_the_right_size_and_wrong_content_is_not_verified(
    tmp_path: Path,
) -> None:
    entry = published(tmp_path)
    into = tmp_path / "assets"
    into.mkdir()
    (into / "set.sofa").write_bytes(b"x" * entry.size)
    assert not verified(entry, into)


def test_the_default_set_is_registered_as_the_one_the_spike_heard() -> None:
    entry = hrtf.SETS["sadie-d1"]
    assert entry.file == "D1_48K_24bit_256tap_FIR_SOFA.sofa"
    assert entry.sha256.startswith("e6c72a84")
    assert entry.url.startswith("https://sofacoustics.org/")


def test_the_launcher_reads_the_registry_without_importing_the_package() -> None:
    """It runs before the environment exists, so it cannot import the
    package - and the registry has only one home, inside it."""
    probe = (
        "import runpy, sys\n"
        f"launch = runpy.run_path({str(ROOT / 'launch.py')!r}, run_name='probe')\n"
        "sets = launch['hrtf_sets']()\n"
        "print(sorted(sets.SETS), 'immersive' in sys.modules)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "['sadie-d1'] False"


def test_a_download_killed_part_way_never_sits_where_the_loader_looks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl+C mid-download skips every clean-up; the half-file it leaves
    must not have the set's own name, or the loader would find it."""
    entry = published(tmp_path)
    into = tmp_path / "assets"
    into.mkdir()

    class Killed:
        def __enter__(self) -> Killed:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            raise KeyboardInterrupt

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Killed())
    with pytest.raises(KeyboardInterrupt):
        fetch(entry, into)

    assert not (into / entry.file).exists()
    monkeypatch.undo()
    assert fetch(entry, into) == into / entry.file, "and the next fetch recovers"
