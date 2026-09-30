"""The bank and its cache (05, *4*; D-120). Headless.

The set here is synthetic - 300 directions of a smooth pulse, each pair
delayed by its direction's x - so preparing it takes a fraction of a
second, and the cache's behaviour is tested without SADIE II D1's 6 s.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.hrtf import bank as module
from immersive.audio.hrtf.bank import Bank, fft_size, prepare
from immersive.audio.hrtf.sofa import HrirSet
from immersive.core.progress import Cancelled, Progress

TAPS = 128


def fibonacci(count: int) -> npt.NDArray[np.float64]:
    index = np.arange(count) + 0.5
    z = 1.0 - 2.0 * index / count
    azimuth = np.pi * (1.0 + 5.0**0.5) * index
    ring = np.sqrt(1.0 - z * z)
    return np.column_stack([ring * np.cos(azimuth), ring * np.sin(azimuth), z])


def pulse(at: float) -> npt.NDArray[np.float64]:
    base = np.zeros(TAPS)
    base[:9] = np.hanning(11)[1:10]
    k = np.arange(TAPS // 2 + 1)
    return np.fft.irfft(
        np.fft.rfft(base) * np.exp(-2j * np.pi * k * (at - 4.0) / TAPS), n=TAPS
    )


def synthetic(count: int = 300, hash: str = "sha256:" + "ab" * 32) -> HrirSet:
    """A source on the right (+X) delays the left ear, as a head does."""
    directions = fibonacci(count)
    responses = np.stack(
        [
            [pulse(20 + 10 * max(x, 0)), pulse(20 + 10 * max(-x, 0))]
            for x in directions[:, 0]
        ]
    ).astype(np.float32)
    return HrirSet(
        title="synthetic",
        licence="",
        database="",
        directions=directions,
        responses=responses,
        delays=np.zeros((count, 2)),
        source_rate=48_000,
        gain=1.0,
        hash=hash,
    )


@pytest.fixture(autouse=True)
def _coarse_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """The index at 16 cells a face and 4 samples a cell: these tests are
    about the cache, not the index's quality, which test_lookup.py holds at
    its full size. Building it at 393 216 samples took 1 s a preparation."""
    from immersive.audio.hrtf import lookup

    monkeypatch.setattr(lookup, "CELLS", 16)
    monkeypatch.setattr(lookup, "SAMPLES", 2)


def made(result: Any) -> Bank:
    assert isinstance(result, Bank), result
    return result


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """How many times the set is decomposed."""
    calls: list[int] = []
    real = module.decompose

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "decompose", counting)
    return calls


# --------------------------------------------------------------------------- #
# nfft
# --------------------------------------------------------------------------- #


def test_nfft_is_sized_for_the_block_the_taps_and_the_itd() -> None:
    # SADIE II D1: 256 taps, and its largest ITD 38.29 samples (phase 2).
    assert fft_size(512, 256, 38.29) == 1024, "as S0 found"
    assert fft_size(2048, 256, 38.29) == 4096
    # The ITD's term is not decoration: without it this would be 1024.
    assert fft_size(512, 256, 300.0) == 2048


def test_nfft_comes_from_the_sets_own_itd(tmp_path: Path) -> None:
    """At 880 frames a power of two falls between this set's ITD of 10 and
    SADIE's 39, so a constant would size it wrong."""
    result = made(prepare(synthetic(), 880, tmp_path))
    assert result.max_itd == pytest.approx(10.0, abs=0.5)
    assert result.nfft == fft_size(880, TAPS, result.max_itd) == 1024
    assert fft_size(880, TAPS, 39.0) == 2048


# --------------------------------------------------------------------------- #
# the bank
# --------------------------------------------------------------------------- #


def test_each_filter_is_its_minimum_phase_response_zero_padded(tmp_path: Path) -> None:
    """At the calibration's gain (D-128), the same for every direction."""
    from immersive.audio.hrtf.decompose import minimum_phase

    hrirs = synthetic()
    result = made(prepare(hrirs, 512, tmp_path))
    back = np.fft.irfft(result.filters.astype(np.complex128), n=result.nfft, axis=-1)
    scale = 10 ** (result.calibration / 20)
    np.testing.assert_allclose(
        back[..., :TAPS], scale * minimum_phase(hrirs.responses), atol=1e-6 * scale
    )
    assert np.abs(back[..., TAPS:]).max() < 1e-6
    assert result.filters.dtype == np.complex64
    assert result.filters.shape == (300, 2, result.nfft // 2 + 1)


# --------------------------------------------------------------------------- #
# the cache (D-120)
# --------------------------------------------------------------------------- #


def test_a_second_preparation_is_read_not_decomposed(
    tmp_path: Path, counted: list[int]
) -> None:
    hrirs = synthetic()
    fresh = made(prepare(hrirs, 512, tmp_path))
    again = made(prepare(hrirs, 512, tmp_path))
    assert counted == [1]
    np.testing.assert_array_equal(again.filters, fresh.filters)
    np.testing.assert_array_equal(again.itd, fresh.itd)


def test_one_entry_serves_every_block_size(tmp_path: Path, counted: list[int]) -> None:
    hrirs = synthetic()
    small = made(prepare(hrirs, 512, tmp_path))
    large = made(prepare(hrirs, 2048, tmp_path))
    assert counted == [1], "the slow part once"
    assert large.nfft > small.nfft and large.block == 2048
    assert len(list((tmp_path / "hrtf").iterdir())) == 1


def test_a_cached_index_weighs_as_a_fresh_one(tmp_path: Path) -> None:
    hrirs = synthetic()
    fresh = made(prepare(hrirs, 512, tmp_path))
    cached = made(prepare(hrirs, 512, tmp_path))
    queries = fibonacci(997)[::-1].copy()
    out = []
    for lookup in (fresh.lookup, cached.lookup):
        vertices = np.zeros((997, 3), dtype=np.int64)
        weights = np.zeros((997, 3))
        lookup.weigh(queries, vertices, weights)
        out.append((vertices, weights))
    np.testing.assert_array_equal(out[0][0], out[1][0])
    np.testing.assert_array_equal(out[0][1], out[1][1])


def entry(tmp_path: Path) -> Path:
    [found] = (tmp_path / "hrtf").iterdir()
    return found


def rewritten(path: Path, **changes: Any) -> None:
    with np.load(path, allow_pickle=False) as stored:
        arrays = {key: stored[key] for key in stored.files}
    arrays.update({key: np.asarray(value) for key, value in changes.items()})
    with path.open("wb") as file:
        np.savez(file, **arrays)


@pytest.mark.parametrize(
    "spoil",
    [
        lambda path: path.write_bytes(path.read_bytes()[: path.stat().st_size // 2]),
        lambda path: path.write_bytes(b""),
        lambda path: rewritten(path, format=99),
        lambda path: rewritten(path, hash="sha256:" + "cd" * 32),
        lambda path: rewritten(path, count=12),
    ],
    ids=["truncated", "empty", "another format", "another set", "another size"],
)
def test_an_entry_amiss_is_prepared_again_and_nothing_raises(
    tmp_path: Path, counted: list[int], spoil: Any
) -> None:
    hrirs = synthetic()
    made(prepare(hrirs, 512, tmp_path))
    spoil(entry(tmp_path))
    made(prepare(hrirs, 512, tmp_path))
    assert counted == [1, 1]


def test_a_cancel_stops_the_decomposition_between_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from immersive.audio.hrtf import decompose

    monkeypatch.setattr(decompose, "CHUNK", 50)  # six chunks of 300
    seen: list[float] = []

    class Stopping(Progress):
        def reach(self, fraction: float) -> None:
            super().reach(fraction)
            seen.append(fraction)
            if len(seen) == 3:
                self.cancelled = True

    result = prepare(synthetic(), 512, tmp_path, Stopping().part(0.0, 1.0))
    assert isinstance(result, Cancelled)
    assert len(seen) == 3, "stopped at the next chunk, not the end"
    assert not (tmp_path / "hrtf").exists(), "and nothing cached"


def test_a_cancel_while_directions_are_indexed_caches_nothing(tmp_path: Path) -> None:
    class Stopping(Progress):
        def reach(self, fraction: float) -> None:
            super().reach(fraction)
            if fraction >= module.DECOMPOSED:
                self.cancelled = True

    result = prepare(synthetic(), 512, tmp_path, Stopping().part(0.0, 1.0))
    assert isinstance(result, Cancelled)
    assert not (tmp_path / "hrtf").exists()
