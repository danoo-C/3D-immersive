"""A SOFA file into an `HrirSet` (05, *1. Load*): the axes, the rate, the
delays, the level, and the refusals. Headless.

Every set here is written by the test with `sofar`, small, with each
measurement's response an impulse at its own tap - so where a direction
landed can be read off the response that came with it. The real set is
tested where it has been fetched, and skipped where it has not.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import sofar

from immersive.assets.hrtf import Builtin
from immersive.audio.hrtf import sofa
from immersive.audio.hrtf.sofa import EAR_ENERGY, HrirSet, builtin, load
from immersive.core.io.media import Refused, content_hash
from immersive.core.time import SAMPLE_RATE

TAPS = 32

#: SOFA azimuth and elevation, and where each is in the project's axes.
CARDINAL = [
    ((0.0, 0.0), (0.0, 1.0, 0.0)),  # front
    ((90.0, 0.0), (-1.0, 0.0, 0.0)),  # left
    ((270.0, 0.0), (1.0, 0.0, 0.0)),  # right
    ((180.0, 0.0), (0.0, -1.0, 0.0)),  # behind
    ((0.0, 90.0), (0.0, 0.0, 1.0)),  # above
    ((0.0, -90.0), (0.0, 0.0, -1.0)),  # below
]


def marked(count: int, level: float = 0.5) -> npt.NDArray[np.float64]:
    """Measurement `m`'s responses: an impulse at tap `m + 1`, both ears."""
    responses = np.zeros((count, 2, TAPS))
    for m in range(count):
        responses[m, :, m + 1] = level
    return responses


def written(
    path: Path,
    positions: npt.NDArray[np.float64],
    responses: npt.NDArray[np.float64],
    *,
    rate: float = SAMPLE_RATE,
    delay: npt.NDArray[np.float64] | None = None,
    cartesian: bool = False,
    convention: str = "SimpleFreeFieldHRIR",
) -> Path:
    made = sofar.Sofa(convention)
    made.Data_IR = responses
    made.Data_SamplingRate = rate
    made.SourcePosition = positions
    if cartesian:
        made.SourcePosition_Type = "cartesian"
        made.SourcePosition_Units = "metre"
    if delay is not None:
        made.Data_Delay = delay
    made.GLOBAL_License = "Test licence 1.0, in the file's own words"
    made.GLOBAL_Title = "A test set"
    made.GLOBAL_DatabaseName = "Tests"
    sofar.write_sofa(str(path), made, compression=0)
    return path


def cardinal(tmp_path: Path, **options: object) -> Path:
    positions = np.array([[az, el, 1.5] for (az, el), _ in CARDINAL])
    return written(tmp_path / "set.sofa", positions, marked(len(CARDINAL)), **options)  # type: ignore[arg-type]


def loaded(path: Path) -> HrirSet:
    result = load(path)
    assert isinstance(result, HrirSet), result
    return result


# --------------------------------------------------------------------------- #
# what comes out
# --------------------------------------------------------------------------- #


def test_every_direction_lands_in_the_projects_axes(tmp_path: Path) -> None:
    """SOFA faces +x with +y left; the project faces +Y with +X right."""
    result = loaded(cardinal(tmp_path))
    for m, (_, expected) in enumerate(CARDINAL):
        tap = int(np.argmax(np.abs(result.responses[m, 0])))
        assert tap == m + 1, "each response still with its own direction"
        np.testing.assert_allclose(result.directions[m], expected, atol=1e-12)


def test_cartesian_positions_land_in_the_same_axes(tmp_path: Path) -> None:
    positions = np.array([[2.0, 0.0, 0.0], [0.0, 1.5, 0.0], [0.0, 0.0, -3.0]])
    result = loaded(
        written(tmp_path / "set.sofa", positions, marked(3), cartesian=True)
    )
    np.testing.assert_allclose(
        result.directions, [[0, 1, 0], [-1, 0, 0], [0, 0, -1]], atol=1e-12
    )


def test_the_licence_title_and_hash_are_the_files_own(tmp_path: Path) -> None:
    path = cardinal(tmp_path)
    result = loaded(path)
    assert result.licence == "Test licence 1.0, in the file's own words"
    assert (result.title, result.database) == ("A test set", "Tests")
    assert result.hash == content_hash(path)
    assert result.responses.dtype == np.float32
    assert result.responses.shape == (len(CARDINAL), 2, TAPS)
    assert result.source_rate == SAMPLE_RATE


def test_a_set_at_44_1_khz_comes_back_at_48(tmp_path: Path) -> None:
    result = loaded(cardinal(tmp_path, rate=44_100))
    assert result.source_rate == 44_100
    assert result.count == len(CARDINAL)
    assert abs(result.taps - TAPS * SAMPLE_RATE / 44_100) <= 1
    for m in range(len(CARDINAL)):
        peak = int(np.argmax(np.abs(result.responses[m, 0])))
        assert abs(peak - (m + 1) * SAMPLE_RATE / 44_100) <= 1, "each where it was"


def test_stored_delays_are_kept_in_samples_at_48_khz(tmp_path: Path) -> None:
    delay = np.array([[m, 2.0 * m] for m in range(len(CARDINAL))], dtype=float)
    result = loaded(cardinal(tmp_path, rate=44_100, delay=delay))
    np.testing.assert_allclose(result.delays, delay * SAMPLE_RATE / 44_100)

    (tmp_path / "shared").mkdir()
    shared = loaded(cardinal(tmp_path / "shared", delay=np.array([[3.0, 5.0]])))
    assert shared.delays.shape == (len(CARDINAL), 2)
    np.testing.assert_allclose(shared.delays[:, 1], 5.0)


# --------------------------------------------------------------------------- #
# the level
# --------------------------------------------------------------------------- #


def test_every_set_is_scaled_to_the_same_mean_ear_energy(tmp_path: Path) -> None:
    positions = np.array([[az, el, 1.5] for (az, el), _ in CARDINAL])
    quiet = loaded(written(tmp_path / "quiet.sofa", positions, marked(6, 0.1)))
    loud = loaded(written(tmp_path / "loud.sofa", positions, marked(6, 0.3)))

    for result in (quiet, loud):
        energy = float(np.mean(np.sum(result.responses.astype(float) ** 2, axis=2)))
        # S0's number, as a literal: the constant alone would move with it.
        assert energy == pytest.approx(0.25) == EAR_ENERGY
    np.testing.assert_allclose(quiet.responses, loud.responses, rtol=1e-6)
    assert quiet.gain == pytest.approx(3 * loud.gain), "and says by how much"


# --------------------------------------------------------------------------- #
# refusals: never raised
# --------------------------------------------------------------------------- #


def test_another_convention_is_refused_by_name(tmp_path: Path) -> None:
    made = sofar.Sofa("GeneralFIR")
    path = tmp_path / "general.sofa"
    sofar.write_sofa(str(path), made, compression=0)
    result = load(path)
    assert isinstance(result, Refused) and "GeneralFIR" in result.reason


@pytest.mark.parametrize("contents", [b"", b"not a SOFA file at all" * 10])
def test_a_file_that_is_not_sofa_is_refused(tmp_path: Path, contents: bytes) -> None:
    path = tmp_path / "set.sofa"
    path.write_bytes(contents)
    assert isinstance(load(path), Refused)


def test_nothing_there_and_a_folder_are_refused(tmp_path: Path) -> None:
    assert load(tmp_path / "gone.sofa") == Refused(
        str(tmp_path / "gone.sofa"), "is not there"
    )
    assert isinstance(load(tmp_path), Refused)


def test_a_silent_set_is_refused(tmp_path: Path) -> None:
    positions = np.array([[0.0, 0.0, 1.5]])
    result = load(written(tmp_path / "set.sofa", positions, np.zeros((1, 2, TAPS))))
    assert isinstance(result, Refused) and "no sound" in result.reason


# --------------------------------------------------------------------------- #
# the built-in set
# --------------------------------------------------------------------------- #


def test_an_unknown_builtin_is_refused() -> None:
    assert isinstance(builtin("no-such-set"), Refused)


def test_a_builtin_not_fetched_says_how_to_fetch_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = Builtin("sadie-d1", "not-fetched.sofa", "", "", 0, "SADIE II D1")
    monkeypatch.setitem(sofa.SETS, "sadie-d1", missing)
    result = builtin("sadie-d1")
    assert isinstance(result, Refused) and "launch.py --install" in result.reason


@pytest.fixture(scope="module")
def sadie() -> HrirSet:
    result = builtin("sadie-d1")
    if isinstance(result, Refused):
        pytest.skip("SADIE II D1 is not fetched here: launch.py --install")
    return result


def test_sadie_ii_d1_is_apache_2_by_its_own_words(sadie: HrirSet) -> None:
    assert "Apache License, Version 2.0" in sadie.licence
    assert sadie.title == "D1 HRIRs"


def test_sadie_ii_d1_is_the_full_sphere_the_spike_heard(sadie: HrirSet) -> None:
    assert (sadie.count, sadie.taps, sadie.source_rate) == (8802, 256, SAMPLE_RATE)
    assert sadie.directions[:, 2].min() == pytest.approx(-1.0)
    assert sadie.directions[:, 2].max() == pytest.approx(1.0)
    np.testing.assert_allclose(np.linalg.norm(sadie.directions, axis=1), 1.0)


def test_sadie_ii_d1_normalised_peaks_under_full_scale(sadie: HrirSet) -> None:
    energy = float(np.mean(np.sum(sadie.responses.astype(float) ** 2, axis=2)))
    assert energy == pytest.approx(EAR_ENERGY)
    assert float(np.abs(sadie.responses).max()) < 1.0
