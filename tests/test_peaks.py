"""Peaks: the pyramid, and the cache that keeps it. Headless (N-5).

The pyramid is checked against a brute-force oracle - a Python loop over
explicit slices of the audio, sharing no code with the vectorised build - so
that the two cannot be wrong the same way.
"""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from immersive.core.io import peaks
from immersive.core.io.media import content_hash
from immersive.core.io.peaks import BUCKET, RATIO, Pyramid, build, cache_directory


def signal(frames: int, channels: int = 1, seed: int = 0) -> npt.NDArray[np.float32]:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, (frames, channels)).astype(np.float32)


def oracle(
    audio: npt.NDArray[np.float32], bucket: int
) -> tuple[list[list[float]], list[list[float]]]:
    """Min and max of each explicit slice, one bucket at a time."""
    lows, highs = [], []
    for start in range(0, len(audio), bucket):
        covered = audio[start : start + bucket]
        lows.append([float(covered[:, c].min()) for c in range(audio.shape[1])])
        highs.append([float(covered[:, c].max()) for c in range(audio.shape[1])])
    return lows, highs


def assert_matches_oracle(pyramid: Pyramid, audio: npt.NDArray[np.float32]) -> None:
    for level in pyramid.levels:
        lows, highs = oracle(audio, level.bucket)
        assert level.buckets == len(lows), f"level of {level.bucket}"
        np.testing.assert_array_equal(level.low, np.array(lows, dtype=np.float32))
        np.testing.assert_array_equal(level.high, np.array(highs, dtype=np.float32))


LENGTHS = [
    1,
    BUCKET - 1,
    BUCKET,
    BUCKET + 1,
    BUCKET * RATIO,
    BUCKET * RATIO**3 + 17,  # several levels' worth, and a remainder
    100_003,
]


@pytest.mark.parametrize("frames", LENGTHS)
def test_every_bucket_of_every_level_is_its_frames_min_and_max(frames: int) -> None:
    audio = signal(frames, seed=frames)

    assert_matches_oracle(build(audio), audio)


@pytest.mark.parametrize("frames", LENGTHS)
def test_the_last_level_is_the_whole_file(frames: int) -> None:
    audio = signal(frames, seed=frames + 1)

    top = build(audio).levels[-1]

    assert top.buckets == 1
    assert top.low[0, 0] == audio.min()
    assert top.high[0, 0] == audio.max()


def test_each_level_is_four_times_coarser(frames: int = 100_003) -> None:
    pyramid = build(signal(frames))

    buckets = [level.bucket for level in pyramid.levels]
    assert buckets == [BUCKET * RATIO**k for k in range(len(buckets))]
    assert len(buckets) == 1 + math.ceil(math.log(frames / BUCKET, RATIO))


def test_the_end_of_a_sample_is_not_drawn_as_silence() -> None:
    """The remainder is its own short bucket, not dropped."""
    audio = np.zeros((BUCKET + 3, 1), dtype=np.float32)
    audio[-1, 0] = 0.9

    level = build(audio).levels[0]

    assert level.buckets == 2
    assert level.high[-1, 0] == pytest.approx(0.9)


def test_stereo_keeps_a_pyramid_per_channel() -> None:
    audio = np.zeros((BUCKET * 8, 2), dtype=np.float32)
    audio[:, 0] = 0.25
    audio[:, 1] = -0.5

    pyramid = build(audio)

    assert pyramid.channels == 2
    for level in pyramid.levels:
        assert (level.high[:, 0] == 0.25).all()
        assert (level.low[:, 1] == -0.5).all()
    assert_matches_oracle(pyramid, audio)


def test_overs_survive() -> None:
    """A float file may hold 2.0 (phase 2), and the drawing must show it."""
    audio = np.array([[2.0], [-3.0]], dtype=np.float32)

    top = build(audio).levels[-1]

    assert (top.low[0, 0], top.high[0, 0]) == (-3.0, 2.0)


def test_the_levels_are_float32() -> None:
    for level in build(signal(5_000)).levels:
        assert level.low.dtype == level.high.dtype == np.float32


def test_nothing_has_no_peaks() -> None:
    """decode() refuses empty files, so this is a caller's mistake."""
    with pytest.raises(ValueError):
        build(np.zeros((0, 1), dtype=np.float32))


def test_the_constants_are_the_documented_ones() -> None:
    """Pinned: changing either is a cache format change."""
    assert (peaks.BUCKET, peaks.RATIO) == (256, 4)


# --------------------------------------------------------------------------- #
# the cache
# --------------------------------------------------------------------------- #

KEY = "sha256:" + "ab" * 32


def counting(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count builds, so a cache hit is asserted rather than timed."""
    built: list[int] = []
    real: Callable[..., Pyramid] = peaks.build

    def build_and_count(audio: npt.NDArray[np.float32]) -> Pyramid:
        built.append(1)
        return real(audio)

    monkeypatch.setattr(peaks, "build", build_and_count)
    return built


def entries(directory: Path) -> list[Path]:
    return (
        sorted((directory / "peaks").glob("*"))
        if (directory / "peaks").exists()
        else []
    )


def assert_same_pyramid(first: Pyramid, second: Pyramid) -> None:
    assert (first.frames, first.channels) == (second.frames, second.channels)
    assert len(first.levels) == len(second.levels)
    for a, b in zip(first.levels, second.levels, strict=True):
        assert a.bucket == b.bucket
        np.testing.assert_array_equal(a.low, b.low)
        np.testing.assert_array_equal(a.high, b.high)


def test_the_second_request_reads_rather_than_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built = counting(monkeypatch)
    audio = signal(50_000, 2)

    first = peaks.peaks(KEY, audio, tmp_path)
    second = peaks.peaks(KEY, audio, tmp_path)

    assert built == [1]
    assert_same_pyramid(first, second)


def test_the_same_audio_at_two_paths_is_one_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-9: computed once per *file*, whichever path or project it is under."""
    built = counting(monkeypatch)
    contents = np.random.default_rng(9).bytes(4_000)
    here, there = tmp_path / "a" / "kick.wav", tmp_path / "b" / "copy.wav"
    for path in (here, there):
        path.parent.mkdir()
        path.write_bytes(contents)
    audio = signal(4_000)

    for path in (here, there):
        key = content_hash(path)
        assert isinstance(key, str)
        peaks.peaks(key, audio, tmp_path / "cache")

    assert built == [1]
    assert len(entries(tmp_path / "cache")) == 1


def damaged_entry(directory: Path, kind: str, audio: npt.NDArray[np.float32]) -> Path:
    entry = directory / "peaks" / ("sha256-" + "ab" * 32 + ".npz")
    entry.parent.mkdir(parents=True)
    if kind == "garbage":
        entry.write_bytes(b"not a cache entry at all")
    elif kind == "empty":
        entry.write_bytes(b"")
    else:
        pyramid = build(audio if kind != "other length" else signal(len(audio) + 1))
        peaks._write(entry, pyramid)
        if kind == "truncated":
            entry.write_bytes(entry.read_bytes()[: entry.stat().st_size // 2])
        elif kind == "other version":
            with np.load(entry) as stored:
                arrays = dict(stored)
            arrays["format"] = np.asarray(peaks.FORMAT + 1)
            with entry.open("wb") as file:
                np.savez(file, **arrays)
    return entry


@pytest.mark.parametrize(
    "kind", ["garbage", "empty", "truncated", "other version", "other length"]
)
def test_a_damaged_entry_is_rebuilt_and_nothing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    audio = signal(20_000)
    damaged_entry(tmp_path, kind, audio)
    built = counting(monkeypatch)

    pyramid = peaks.peaks(KEY, audio, tmp_path)
    assert built == [1]
    assert_matches_oracle(pyramid, audio)

    peaks.peaks(KEY, audio, tmp_path)
    assert built == [1], "and rewritten, so the next request reads"


def test_an_interrupted_write_leaves_no_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half a file at the entry's name would be read later as a real one."""

    def disk_full(file: object, **arrays: object) -> None:
        assert hasattr(file, "write")
        file.write(b"PK\x03\x04 the first few bytes of a zip")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(peaks.np, "savez", disk_full)

    pyramid = peaks.peaks(KEY, signal(3_000), tmp_path)

    assert pyramid.frames == 3_000, "the peaks are still returned"
    assert entries(tmp_path) == [], "no entry, and no temporary file left over"


def test_a_key_cannot_leave_the_cache(tmp_path: Path) -> None:
    """The key becomes a file name; only a content hash is accepted."""
    with pytest.raises(ValueError):
        peaks.peaks("sha256:../../etc", signal(10), tmp_path)


def test_the_suites_cache_is_inside_its_temporary_home() -> None:
    """D-91's reason, asserted: this holds on every platform, because the
    code reads the variables `conftest.py` redirects rather than asking Qt."""
    assert cache_directory().is_relative_to(Path(os.environ["HOME"]))


@pytest.mark.parametrize(
    ("platform", "variables", "expected"),
    [
        ("linux", {"XDG_CACHE_HOME": "/x/cache"}, "/x/cache/3dimmersive"),
        ("linux", {"XDG_CACHE_HOME": ""}, "/home/h/.cache/3dimmersive"),
        ("darwin", {}, "/home/h/Library/Caches/3dimmersive"),
        ("win32", {"LOCALAPPDATA": "/x/Local"}, "/x/Local/3dImmersive/Cache"),
    ],
)
def test_the_directory_follows_03s_table(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    variables: dict[str, str],
    expected: str,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/h")))
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    assert cache_directory().as_posix() == expected
