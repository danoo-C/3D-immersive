"""Decoding and resampling. Headless, like everything in `core/` (N-5).

Every fixture is generated here rather than committed: libsndfile writes all
five of F-5's formats, MP3 included (D-86). And because the library that
writes a fixture is the one that reads it back, no assertion here compares
the two - M1 phase 5's lesson that a round trip proves only that a reader and
a writer agree. What is asserted is independent of both: a frame count worked
out by hand, a tone's frequency measured by FFT, a value that should not have
changed at all.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import soundfile

from immersive.core.io import media
from immersive.core.io.media import Decoded, Refused, decode, frames_at_project_rate
from immersive.core.time import SAMPLE_RATE


def tone(
    rate: int, seconds: float = 1.0, hz: float = 1000.0, amplitude: float = 0.5
) -> npt.NDArray[np.float32]:
    t = np.arange(round(rate * seconds)) / rate
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def written(
    path: Path,
    audio: npt.NDArray[np.float32],
    rate: int,
    *,
    format: str | None = None,
    subtype: str | None = None,
) -> Path:
    soundfile.write(path, audio, rate, format=format, subtype=subtype)
    return path


def decoded(path: Path) -> Decoded:
    result = decode(path)
    assert isinstance(result, Decoded), result
    return result


def refused(path: Path) -> Refused:
    result = decode(path)
    assert isinstance(result, Refused), f"{path.name} decoded"
    return result


# --------------------------------------------------------------------------- #
# F-5's formats
# --------------------------------------------------------------------------- #

LOSSLESS = [
    ("WAV", "PCM_16", "wav"),
    ("AIFF", "PCM_16", "aiff"),
    ("FLAC", "PCM_16", "flac"),
]
LOSSY = [("OGG", "VORBIS", "ogg"), ("MP3", "MPEG_LAYER_III", "mp3")]


@pytest.mark.parametrize(("format", "subtype", "suffix"), LOSSLESS + LOSSY)
def test_every_format_f5_names_decodes(
    tmp_path: Path, format: str, subtype: str, suffix: str
) -> None:
    path = written(
        tmp_path / f"tone.{suffix}",
        tone(SAMPLE_RATE),
        SAMPLE_RATE,
        format=format,
        subtype=subtype,
    )

    result = decoded(path)

    assert result.channels == 1
    if (format, subtype, suffix) in LOSSLESS:
        assert result.frames == SAMPLE_RATE
    else:
        # A lossy codec may pad or trim a frame's worth; a second is still one.
        assert abs(result.frames - SAMPLE_RATE) < SAMPLE_RATE * 0.005


def test_mp3_is_readable_on_this_platform() -> None:
    """D-86's evidence, gathered wherever the suite runs - every CI leg.

    The decision to carry no fallback decoder is only as good as the
    libsndfile each platform's wheel ships, and this is where one without
    MP3 would show.
    """
    assert "MP3" in soundfile.available_formats()


# --------------------------------------------------------------------------- #
# what comes back
# --------------------------------------------------------------------------- #


def test_the_audio_is_float32_frames_by_channels_contiguous_and_read_only(
    tmp_path: Path,
) -> None:
    """Read-only because every clip of this sample shares the one array."""
    result = decoded(written(tmp_path / "a.wav", tone(SAMPLE_RATE), SAMPLE_RATE))

    assert result.audio.dtype == np.float32
    assert result.audio.shape == (SAMPLE_RATE, 1)
    assert result.audio.flags["C_CONTIGUOUS"]
    with pytest.raises(ValueError):
        result.audio[0, 0] = 1.0


def test_stereo_stays_two_channels(tmp_path: Path) -> None:
    left, right = tone(SAMPLE_RATE, hz=440.0), tone(SAMPLE_RATE, hz=660.0)
    stereo = np.stack([left, right], axis=1)

    result = decoded(written(tmp_path / "s.wav", stereo, SAMPLE_RATE, subtype="FLOAT"))

    assert result.audio.shape == (SAMPLE_RATE, 2)
    np.testing.assert_array_equal(result.audio[:, 1], right)


def test_a_48k_source_comes_back_untouched(tmp_path: Path) -> None:
    """No resampling pass at all - a no-op filter still moves samples."""
    noise = np.random.default_rng(1).uniform(-0.9, 0.9, (4801, 2)).astype(np.float32)

    result = decoded(written(tmp_path / "n.wav", noise, SAMPLE_RATE, subtype="FLOAT"))

    np.testing.assert_array_equal(result.audio, noise)


@pytest.mark.parametrize("subtype", ["PCM_16", "PCM_24"])
def test_integer_sources_come_back_within_one(tmp_path: Path, subtype: str) -> None:
    """The phase's ±1, and it holds by construction for integer formats."""
    extremes = np.array([[1.0], [-1.0], [0.0]] * 100, dtype=np.float32)

    result = decoded(
        written(tmp_path / "x.wav", extremes, SAMPLE_RATE, subtype=subtype)
    )

    assert result.audio.max() <= 1.0
    assert result.audio.min() == -1.0


def test_a_float_source_above_full_scale_passes_through(tmp_path: Path) -> None:
    """Not clipped. A float file may legitimately hold 2.0, and clipping it on
    import would change the audio before anyone heard it - overs are the
    master limiter's (D-54). The plan says why the phase's ±1 is read this way.
    """
    loud = np.array([[1.5], [-2.0], [0.25]], dtype=np.float32)

    result = decoded(written(tmp_path / "loud.wav", loud, SAMPLE_RATE, subtype="FLOAT"))

    np.testing.assert_array_equal(result.audio, loud)


# --------------------------------------------------------------------------- #
# resampling
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("rate", [22_050, 44_100, 96_000])
def test_a_second_at_any_rate_is_a_second_at_48k(tmp_path: Path, rate: int) -> None:
    result = decoded(written(tmp_path / "t.wav", tone(rate), rate, subtype="FLOAT"))

    assert result.frames == SAMPLE_RATE
    assert result.source_rate == rate


def test_an_awkward_length_follows_the_rule_exactly(tmp_path: Path) -> None:
    """1 000 003 frames at 44.1 kHz is 1 088 438.639… at 48 kHz: 1 088 439."""
    audio = np.zeros(1_000_003, dtype=np.float32)

    result = decoded(written(tmp_path / "long.wav", audio, 44_100, subtype="FLOAT"))

    assert result.frames == 1_088_439


@pytest.mark.parametrize(
    ("frames", "rate", "expected"),
    [
        (44_100, 44_100, 48_000),
        (7, 44_100, 8),  # 7.619…
        (7, 96_000, 4),  # 3.5 exactly - half rounds up
        (1, 96_000, 1),  # 0.5 exactly
        (1_000_003, 22_050, 2_176_877),  # 2 176 877.279…
        (1_000_003, 96_000, 500_002),  # 500 001.5
    ],
)
def test_the_frame_rule(frames: int, rate: int, expected: int) -> None:
    """Worked by hand, including the two exact halves, which are the cases a
    float product can land either side of."""
    assert frames_at_project_rate(frames, rate) == expected


def test_resampling_keeps_the_pitch(tmp_path: Path) -> None:
    """A 1 kHz tone at 44.1 kHz is still 1 kHz at 48 - measured, not assumed.

    A missing resample would put the peak at 1088 Hz: 44.1 kHz material
    played eight percent fast.
    """
    result = decoded(
        written(tmp_path / "t.wav", tone(44_100, hz=1000.0), 44_100, subtype="FLOAT")
    )

    spectrum = np.abs(np.fft.rfft(result.audio[:, 0]))
    peak_hz = np.argmax(spectrum) * SAMPLE_RATE / result.frames
    assert abs(peak_hz - 1000.0) <= 1.0


# --------------------------------------------------------------------------- #
# what a pool entry records
# --------------------------------------------------------------------------- #


def test_the_media_file_records_what_decoding_found(tmp_path: Path) -> None:
    path = written(tmp_path / "kick.wav", tone(44_100), 44_100, subtype="PCM_16")

    entry = decoded(path).media_file("m-00000001", path)

    assert entry.id == "m-00000001"
    assert entry.name == "kick.wav", "the whole name - kick.mp3 is another sample"
    assert Path(entry.path) == path.absolute()
    assert entry.source_rate == 44_100, "the file's rate, not the project's"
    assert entry.channels == 1
    assert entry.frames == SAMPLE_RATE
    assert entry.hash == "", "phase 3's"


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #


def test_a_file_that_is_not_there(tmp_path: Path) -> None:
    result = refused(tmp_path / "gone.wav")

    assert result.reason == "is not there"
    assert str(result) == "gone.wav: is not there"


def test_a_folder(tmp_path: Path) -> None:
    folder = tmp_path / "samples.wav"
    folder.mkdir()

    assert "folder" in refused(folder).reason


@pytest.mark.parametrize(
    "contents",
    [b"", b"hello, this is not audio\n" * 20, b"RIFF\x24\x00\x00\x00WAVEfmt "],
    ids=["empty", "text", "header only"],
)
def test_a_file_that_is_not_audio(tmp_path: Path, contents: bytes) -> None:
    path = tmp_path / "fake.wav"
    path.write_bytes(contents)

    assert refused(path).reason.startswith("is not a sound file this can read")


def test_a_file_with_no_frames(tmp_path: Path) -> None:
    path = written(tmp_path / "empty.wav", np.zeros((0, 1), np.float32), SAMPLE_RATE)

    assert refused(path).reason == "contains no audio"


def test_more_than_two_channels_is_refused_not_folded(tmp_path: Path) -> None:
    """D-87: a guess at a downmix sounds plausible and is wrong."""
    path = written(tmp_path / "six.wav", np.zeros((100, 6), np.float32), SAMPLE_RATE)

    assert refused(path).reason == (
        "has 6 channels; only mono and stereo can be imported"
    )


HOSTILE = [
    b"\x00" * 64,
    bytes(range(256)) * 4,
    b"RIFF\xff\xff\xff\x7fWAVEfmt \x10\x00\x00\x00\x01\x00\x02\x00",
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x10\x00data\x00\x00\x00\x00",
    b"fLaC" + b"\xff" * 60,
    b"OggS" + b"\x00" * 60,
    b"ID3\x04\x00\x00\x00\x00\x00\x10" + b"\xff\xfb" * 40,
    b"FORM\x00\x00\x00\x04AIFF",
    np.random.default_rng(7).bytes(4096),
]


@pytest.mark.parametrize("contents", HOSTILE)
@pytest.mark.parametrize("suffix", ["wav", "flac", "mp3"])
def test_nothing_raises(tmp_path: Path, contents: bytes, suffix: str) -> None:
    """One bad file must not stop a folder import. Decoded or refused, never
    an exception."""
    path = tmp_path / f"hostile.{suffix}"
    path.write_bytes(contents)

    assert isinstance(decode(path), (Decoded, Refused))


def test_the_resampler_quality_is_the_documented_one() -> None:
    """The plan chose `HQ` over `VHQ` against N-4's load budget; pinned so a
    change is a decision someone writes down rather than an edit."""
    assert media.QUALITY == "HQ"
