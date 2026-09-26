"""The player: one stream, the transport's, carrying audition too (D-107).

Driven through the stand-in in `standin.py`, so nothing here needs
PortAudio or a device. M2's audition tests, moved here with it: a sample
still plays from its first frame, mono to both ears, and a second replaces
the first - but through the engine now, and on a stream that stays open.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
import soundfile

import immersive
from immersive.app import build_application
from immersive.audio.device import Output, load_backend
from immersive.audio.dsp import ramp_steps
from immersive.audio.engine import RING
from immersive.audio.player import LOST, Player
from immersive.core.time import SAMPLE_RATE
from immersive.ui.main_window import MainWindow
from immersive.ui.notices import Severity
from standin import Backend, Stream, ramp

BLOCK = 64


@pytest.fixture
def backend() -> Backend:
    return Backend()


@pytest.fixture
def player(backend: Backend) -> Player:
    return Player(backend, Output(device=None, block=BLOCK))


# --------------------------------------------------------------------------- #
# the stream
# --------------------------------------------------------------------------- #


def test_the_stream_is_opened_at_48k_and_nothing_else(
    backend: Backend, player: Player
) -> None:
    player.audition(ramp(10))

    [stream] = backend.streams
    assert stream.settings["samplerate"] == SAMPLE_RATE
    assert stream.settings["blocksize"] == BLOCK
    assert stream.settings["channels"] == 2
    assert stream.settings["dtype"] == "float32"
    assert stream.active and player.running


def test_the_flags_reach_the_stream(backend: Backend) -> None:
    Player(backend, Output(device="Headphones", block=1024)).play()

    [stream] = backend.streams
    assert (stream.settings["device"], stream.settings["blocksize"]) == (
        "Headphones",
        1024,
    )


def test_nothing_opens_a_stream_until_something_is_to_be_heard(
    backend: Backend, player: Player
) -> None:
    player.seek(4_000)
    player.set_loop(0, 1_000, True)
    player.pause()
    assert backend.streams == [] and not player.running
    assert player.playhead == 4_000, "applied with no stream to drain them"


def test_with_no_stream_the_ring_never_fills(backend: Backend, player: Player) -> None:
    """The window sends the repeat's end at every edit (D-111): with no
    stream those would fill the ring, and a seek after them would be lost."""
    for _ in range(RING + 1):
        player.set_repeat(96_000, True)
    player.seek(4_000)
    assert player.playhead == 4_000


def test_play_and_audition_share_the_one_stream(
    backend: Backend, player: Player
) -> None:
    player.play()
    player.audition(ramp(10))
    player.pause()
    player.audition(ramp(10))
    assert len(backend.streams) == 1


def stream(backend: Backend) -> Stream:
    [only] = backend.streams
    return only


# --------------------------------------------------------------------------- #
# audition, through the engine
# --------------------------------------------------------------------------- #


def test_the_frames_go_out_in_order(backend: Backend, player: Player) -> None:
    sample = ramp(BLOCK * 3, channels=2)
    player.audition(sample)

    written = np.concatenate([stream(backend).block() for _ in range(3)])

    np.testing.assert_array_equal(written, sample)


def test_mono_goes_to_both_ears(backend: Backend, player: Player) -> None:
    sample = ramp(BLOCK)
    player.audition(sample)

    out = stream(backend).block()

    np.testing.assert_array_equal(out[:, 0], sample[:, 0])
    np.testing.assert_array_equal(out[:, 1], sample[:, 0])


def test_after_the_last_frame_silence_and_the_stream_stays_open(
    backend: Backend, player: Player
) -> None:
    """D-107: the stream is the transport's, and stays open once needed."""
    sample = ramp(BLOCK + 10)
    player.audition(sample)
    stream(backend).block()

    last = stream(backend).block()

    np.testing.assert_array_equal(last[:10, 0], sample[BLOCK:, 0])
    assert (last[10:] == 0).all(), "silence, not whatever was in the buffer"
    assert stream(backend).active and not stream(backend).closed


def test_a_second_sample_replaces_the_first_from_its_first_frame(
    backend: Backend, player: Player
) -> None:
    player.audition(ramp(BLOCK * 10))
    stream(backend).block()
    stream(backend).block()
    second = ramp(BLOCK * 2, channels=2) * -1

    player.audition(second)
    out = stream(backend).block()

    first_falling = ramp(BLOCK * 10)[2 * BLOCK : 3 * BLOCK] * fall()[:, None]
    np.testing.assert_allclose(out, second[:BLOCK] + first_falling, rtol=1e-6)
    np.testing.assert_array_equal(stream(backend).block(), second[BLOCK:])


def sounding(player: Player) -> bool:
    """`auditioning`, read afresh: mypy would keep an assert's narrowing."""
    return player.auditioning


def fall() -> npt.NDArray[np.float32]:
    return np.float32(1.0) - ramp_steps(BLOCK)


def test_stopping_an_audition_falls_to_silence_and_lets_the_voice_go(
    backend: Backend, player: Player
) -> None:
    player.audition(ramp(BLOCK * 10))
    stream(backend).block()
    assert sounding(player)

    player.stop_audition()

    assert not sounding(player)
    out = stream(backend).block()
    expected = ramp(BLOCK * 10)[BLOCK : 2 * BLOCK] * fall()[:, None]
    np.testing.assert_allclose(out, np.repeat(expected, 2, axis=1), rtol=1e-6)
    assert not stream(backend).block().any()
    player.release()
    assert player._voices == []


def test_a_voice_is_held_until_the_engine_lets_it_go(
    backend: Backend, player: Player
) -> None:
    """So its array is never freed on the audio thread."""
    player.audition(ramp(BLOCK))
    first = player.engine._next_voice
    stream(backend).block()
    player.audition(ramp(BLOCK))
    assert first in player._voices, "the engine still has it until its next block"
    stream(backend).block()
    player.poll()
    assert first not in player._voices


# --------------------------------------------------------------------------- #
# devices that will not play
# --------------------------------------------------------------------------- #


def test_a_device_that_will_not_open_is_reported(backend: Backend) -> None:
    said: list[str] = []
    player = Player(Backend(refuse=True), Output(None, BLOCK), report=said.append)

    assert not player.audition(ramp(10))
    assert not player.play()

    assert said == ["The output device would not open (Device unavailable)"] * 2
    assert not player.playing


def test_a_device_lost_during_playback_stops_holds_and_says_so_once(
    backend: Backend,
) -> None:
    """05: the stream stops, the failure is said, and reopening is the
    person's to do - not a silent move to the laptop speakers."""
    said: list[str] = []
    player = Player(backend, Output(None, BLOCK), report=said.append)
    player.play()
    stream(backend).block()
    stream(backend).block()

    stream(backend).lose()
    assert said == [], "PortAudio's thread only sets a flag"
    player.poll()
    player.poll()

    assert said == [LOST]
    assert not player.playing and not player.running
    assert player.playhead == 2 * BLOCK, "where it was"
    assert stream(backend).closed


def test_play_after_a_lost_device_reopens_and_the_new_stream_is_left_alone(
    backend: Backend,
) -> None:
    said: list[str] = []
    player = Player(backend, Output(None, BLOCK), report=said.append)
    player.play()
    backend.streams[0].lose()
    player.poll()

    assert player.play()
    player.poll()

    assert len(backend.streams) == 2 and backend.streams[1].active
    assert player.running and said == [LOST], "the old loss is not the new stream's"


def test_closing_is_not_reported_as_a_lost_device(backend: Backend) -> None:
    said: list[str] = []
    player = Player(backend, Output(None, BLOCK), report=said.append)
    player.play()
    player.close()
    backend.streams[0].finished()
    player.poll()
    assert said == []


# --------------------------------------------------------------------------- #
# the machine may have no audio stack at all
# --------------------------------------------------------------------------- #


def test_loading_the_backend_never_raises() -> None:
    """On this machine it may be the module or a sentence; never an exception."""
    loaded = load_backend()

    assert isinstance(loaded, str) or hasattr(loaded, "OutputStream")
    if isinstance(loaded, str):
        assert "libportaudio2" in loaded, "and it says what to install"


def test_nothing_imports_sounddevice_at_module_level() -> None:
    """It raises OSError at import without PortAudio - no application at all,
    rather than an application that says what to install."""
    package = Path(immersive.__file__).parent
    offenders = []
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(name.split(".")[0] == "sounddevice" for name in names):
                offenders.append(str(path.relative_to(package)))

    assert offenders == []


# --------------------------------------------------------------------------- #
# in the window
# --------------------------------------------------------------------------- #


@pytest.fixture
def heard(backend: Backend) -> Iterator[MainWindow]:
    build_application([])
    made = MainWindow(player=Player(backend, Output(None, BLOCK)))
    yield made
    made.deleteLater()


def imported_sample(window: MainWindow, tmp_path: Path) -> str:
    import time

    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication

    path = tmp_path / "kick.wav"
    soundfile.write(path, ramp(4_000), SAMPLE_RATE, subtype="FLOAT")
    window.import_paths([path])
    deadline = time.monotonic() + 20
    while window.importing() and time.monotonic() < deadline:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return window.document().project.media_pool[0].id


def pool_id_role() -> int:
    from immersive.ui.explorer.media_pool import ID_ROLE

    return int(ID_ROLE)


@pytest.mark.gui
def test_double_clicking_a_row_plays_it(
    heard: MainWindow, backend: Backend, tmp_path: Path
) -> None:
    media_id = imported_sample(heard, tmp_path)
    pool = heard.pool()
    index = pool.proxy.index(0, 0)
    assert index.data(pool_id_role()) == media_id

    pool.tree.doubleClicked.emit(index)

    out = stream(backend).block()
    np.testing.assert_array_equal(out[:, 0], ramp(4_000)[:BLOCK, 0])


@pytest.mark.gui
def test_a_row_says_how_to_hear_it(heard: MainWindow, tmp_path: Path) -> None:
    imported_sample(heard, tmp_path)

    tip = heard.pool().proxy.index(0, 0).data(3)  # Qt.ToolTipRole

    assert tip.endswith("Double-click to hear it")


@pytest.mark.gui
def test_without_audio_the_window_still_opens_and_says_why(tmp_path: Path) -> None:
    build_application([])
    reason = "Audio output is unavailable (PortAudio not found) - install it"
    window = MainWindow(player=None, unavailable=reason)
    imported_sample(window, tmp_path)

    tip = window.pool().proxy.index(0, 0).data(3)
    assert tip.endswith(f"Cannot be heard: {reason}")
    assert not window.audition_media(window.document().project.media_pool[0].id)
    window.deleteLater()


@pytest.mark.gui
def test_a_device_lost_becomes_one_notice_at_the_next_tick(
    heard: MainWindow, backend: Backend, tmp_path: Path
) -> None:
    media_id = imported_sample(heard, tmp_path)
    heard.audition_media(media_id)
    stream(backend).lose()
    assert heard.notices().newest_first() == []

    heard.tick()
    heard.tick()

    [notice] = heard.notices().newest_first()
    assert notice.severity is Severity.WARN and notice.message == LOST
