"""The engine, block by block, with no device and no window (D-105).

A stand-in is not needed for `process()`: it is called here as the stream
would call it, with a buffer of the stream's shape, and its output read.
`callback` gets a status shaped like `sounddevice`'s.
"""

from __future__ import annotations

import gc
import weakref
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.dsp import db_to_gain
from immersive.audio.engine import RING, Engine, Voice
from immersive.audio.scheduler import Snapshot, build
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, MediaFile, Project

Audio = npt.NDArray[np.float32]
BLOCK = 256
FRAMES = 48_000


def level(value: float, frames: int = FRAMES) -> Audio:
    """A sample that holds one value throughout."""
    audio = np.full((frames, 1), value, dtype=np.float32)
    audio.flags.writeable = False
    return audio


def numbered(frames: int = FRAMES) -> Audio:
    values = (np.arange(frames, dtype=np.float32) + 1) / 65_536
    audio: Audio = np.ascontiguousarray(values[:, None], dtype=np.float32)
    audio.flags.writeable = False
    return audio


def arrangement(*values: float) -> tuple[Project, dict[str, Decoded]]:
    """A channel per value, each playing a whole sample of that one value
    from 0 - the file's own start and end, so no implicit fades."""
    project = Project()
    store: dict[str, Decoded] = {}
    for n, value in enumerate(values):
        media = MediaFile(f"m-0000000{n}", f"/{n}.wav", f"{n}.wav", 48_000, 1, FRAMES)
        project.media_pool.append(media)
        store[media.id] = Decoded(level(value), 48_000)
        project.channels.append(
            Channel(
                f"c-0000000{n}",
                f"C{n}",
                "#A855F7",
                clips=[Clip(f"k-0000000{n}", media.id, 0, 0, FRAMES)],
            )
        )
    return project, store


def snapshot(
    project: Project, store: dict[str, Decoded], previous: Snapshot | None = None
) -> Snapshot:
    return build(project, store.get, previous)


def block(engine: Engine) -> Audio:
    out = np.full((engine.block, 2), np.nan, dtype=np.float32)
    engine.process(out)
    return out


def playing(project: Project, store: dict[str, Decoded]) -> tuple[Engine, Snapshot]:
    engine = Engine(BLOCK)
    snap = snapshot(project, store)
    engine.install(snap)
    engine.set_playing(True)
    return engine, snap


# --------------------------------------------------------------------------- #
# the bus
# --------------------------------------------------------------------------- #


def test_the_bus_is_every_channel_at_its_gain() -> None:
    project, store = arrangement(0.25, 0.125)
    project.channels[0].gain_db = -6.0
    engine, _ = playing(project, store)

    out = block(engine)

    expected = np.float32(0.25) * np.float32(db_to_gain(-6.0)) + np.float32(0.125)
    assert np.allclose(out, expected)
    assert engine.playhead == BLOCK


@pytest.mark.parametrize(
    ("muted", "soloed", "heard"),
    [
        ((), (), (0, 1, 2)),
        ((1,), (), (0, 2)),
        ((), (2,), (2,)),
        ((), (0, 2), (0, 2)),
        ((2,), (0, 2), (0,)),
    ],
)
def test_mute_and_solo_silence_what_audible_says(
    muted: tuple[int, ...], soloed: tuple[int, ...], heard: tuple[int, ...]
) -> None:
    """Values that sum uniquely, so the bus says which channels it heard."""
    values = (0.0625, 0.125, 0.25)
    project, store = arrangement(*values)
    for n in muted:
        project.channels[n].mute = True
    for n in soloed:
        project.channels[n].solo = True
    engine, _ = playing(project, store)
    assert np.allclose(block(engine), sum(values[n] for n in heard))


def test_a_mono_clip_reaches_both_ears() -> None:
    project, store = arrangement(0.5)
    engine, _ = playing(project, store)
    out = block(engine)
    assert np.array_equal(out[:, 0], out[:, 1])


# --------------------------------------------------------------------------- #
# gain through the ring
# --------------------------------------------------------------------------- #


def steps(signal: Audio) -> float:
    return float(np.max(np.abs(np.diff(signal.astype(np.float64)))))


def test_a_gain_change_ramps_across_one_block() -> None:
    project, store = arrangement(1.0)
    engine, snap = playing(project, store)
    assert np.allclose(block(engine), 1.0)

    assert engine.send_gain(snap.generation, 0, 0.5)
    ramped = block(engine)[:, 0]
    after = block(engine)[:, 0]

    assert ramped[0] == pytest.approx(1.0 - 0.5 / BLOCK)
    assert ramped[-1] == pytest.approx(0.5)
    assert steps(ramped) <= 0.5 / BLOCK + 1e-6, "no sample steps past the ramp"
    assert np.allclose(after, 0.5) and steps(after) == 0.0


def test_a_mute_ramps_to_silence_rather_than_clicking() -> None:
    project, store = arrangement(1.0)
    engine, snap = playing(project, store)
    block(engine)
    engine.send_gain(snap.generation, 0, 0.0)
    ramped = block(engine)[:, 0]
    assert ramped[0] > 0.99 and ramped[-1] == 0.0
    assert steps(ramped) <= 1.0 / BLOCK + 1e-6
    assert not block(engine).any()


def test_a_gain_changed_while_a_channel_is_silent_is_in_place_when_it_plays() -> None:
    """Not ramped late, from the old gain, over the clip's first block."""
    project, store = arrangement(1.0)
    project.channels[0].clips[0].start = 3 * BLOCK
    engine, snap = playing(project, store)
    block(engine)
    engine.send_gain(snap.generation, 0, 0.5)
    assert not block(engine).any() and not block(engine).any()

    assert np.allclose(block(engine), 0.5)


def test_a_command_for_another_snapshot_is_dropped() -> None:
    """After a reorder, channel 0 of the old snapshot is someone else."""
    project, store = arrangement(0.25, 0.5)
    engine, first = playing(project, store)
    block(engine)
    project.channels.reverse()
    second = snapshot(project, store, first)
    engine.install(second)
    block(engine)

    engine.send_gain(first.generation, 0, 0.0)

    assert np.allclose(block(engine), 0.75)


def test_a_command_for_a_channel_that_is_not_there_is_dropped() -> None:
    project, store = arrangement(0.25)
    engine, snap = playing(project, store)
    engine.send_gain(snap.generation, 3, 0.0)
    engine.send_gain(snap.generation, -1, 0.0)
    assert np.allclose(block(engine), 0.25)


def test_a_full_ring_refuses_rather_than_overwriting() -> None:
    project, store = arrangement(0.25)
    engine, snap = playing(project, store)
    for _ in range(RING - 1):  # the first slot is the play command
        assert engine.send_gain(snap.generation, 0, 0.5)
    assert not engine.send_gain(snap.generation, 0, 0.0)
    assert not engine.seek(0)
    block(engine)
    assert engine.send_gain(snap.generation, 0, 1.0), "drained, so room again"


# --------------------------------------------------------------------------- #
# snapshots
# --------------------------------------------------------------------------- #


def test_a_snapshot_is_taken_up_at_a_block_boundary_whole() -> None:
    project, store = arrangement(0.25)
    engine, first = playing(project, store)
    block(engine)
    project.channels[0].clips[0].gain_db = 6.0
    engine.install(snapshot(project, store, first))

    out = block(engine)

    expected = np.float32(0.25) * np.float32(db_to_gain(6.0))
    assert np.allclose(out, expected), "every sample of the block the new one's"


def test_a_channels_gain_ramps_on_across_a_new_snapshot() -> None:
    """The snapshot starts where the last one left the channel, so a gain
    changed together with a structural edit does not jump."""
    project, store = arrangement(1.0)
    engine, first = playing(project, store)
    block(engine)
    project.channels[0].gain_db = db_to_gain_db(0.5)
    engine.install(snapshot(project, store, first))

    ramped = block(engine)[:, 0]

    assert ramped[0] == pytest.approx(1.0 - 0.5 / BLOCK, abs=1e-4)
    assert ramped[-1] == pytest.approx(0.5, abs=1e-4)


def db_to_gain_db(gain: float) -> float:
    return float(20 * np.log10(gain))


def test_a_snapshot_built_against_one_never_played_starts_at_its_targets() -> None:
    """Two installed within one block: the second's places count in the
    first, which the engine never took up."""
    project, store = arrangement(1.0, 1.0)
    engine, first = playing(project, store)
    block(engine)
    second = snapshot(project, store, first)
    project.channels.reverse()
    project.channels[0].gain_db = db_to_gain_db(0.5)
    third = snapshot(project, store, second)
    engine.install(second)
    engine.install(third)

    out = block(engine)[:, 0]

    assert np.allclose(out, 1.5), "no ramp from a place that means another channel"


def test_the_engine_lets_go_of_a_snapshot_it_has_moved_past() -> None:
    """It never holds the only reference: whoever installed it does. So a
    snapshot the engine has moved past lives exactly as long as they keep
    it, and is not freed on the audio thread."""
    project, store = arrangement(0.25)
    engine, first = playing(project, store)
    block(engine)
    second = snapshot(project, store, first)
    engine.install(second)
    assert engine.holds(first) and engine.holds(second)

    block(engine)

    assert not engine.holds(first) and engine.holds(second)
    gone = weakref.ref(first)
    del first
    gc.collect()
    assert gone() is None, "the engine kept no reference of its own"


# --------------------------------------------------------------------------- #
# the playhead
# --------------------------------------------------------------------------- #


def test_after_a_seek_the_next_block_starts_at_the_new_playhead() -> None:
    project, store = arrangement(0.0)
    store["m-00000000"] = Decoded(numbered(), 48_000)
    engine, _ = playing(project, store)
    block(engine)
    block(engine)

    assert engine.seek(10_000)
    out = block(engine)[:, 0]

    assert np.array_equal(out, numbered()[10_000 : 10_000 + BLOCK, 0])
    assert engine.playhead == 10_000 + BLOCK


def test_a_seek_and_a_gain_in_one_block_both_apply() -> None:
    project, store = arrangement(1.0)
    engine, snap = playing(project, store)
    engine.seek(5_000)
    engine.send_gain(snap.generation, 0, 0.0)
    block(engine)
    assert engine.playhead == 5_000 + BLOCK
    assert not block(engine).any()


def test_blocks_follow_on_exactly_at_every_size() -> None:
    project, store = arrangement(0.0)
    store["m-00000000"] = Decoded(numbered(), 48_000)
    for size in (256, 512, 2048):
        engine = Engine(size)
        engine.install(snapshot(project, store))
        engine.set_playing(True)
        heard = np.concatenate([block(engine)[:, 0] for _ in range(5)])
        assert np.array_equal(heard, numbered()[: 5 * size, 0])


# --------------------------------------------------------------------------- #
# peaks and xruns
# --------------------------------------------------------------------------- #


def test_the_peaks_are_the_buss_and_are_taken_once() -> None:
    project, store = arrangement(0.25, -0.5)
    project.channels[1].gain_db = -6.0
    engine, _ = playing(project, store)
    block(engine)
    left, right = engine.take_peaks()
    expected = abs(0.25 - 0.5 * db_to_gain(-6.0))
    assert left == pytest.approx(expected, rel=1e-4)
    assert right == pytest.approx(expected, rel=1e-4)
    assert engine.take_peaks() == (0.0, 0.0)


@dataclass
class Status:
    """`sounddevice.CallbackFlags`'s one attribute the engine reads."""

    output_underflow: bool = False


def test_underflows_are_counted() -> None:
    project, store = arrangement(0.25)
    engine, _ = playing(project, store)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    engine.callback(out, BLOCK, None, Status())
    engine.callback(out, BLOCK, None, Status(output_underflow=True))
    engine.callback(out, BLOCK, None, None)
    assert engine.xruns == 1
    assert np.allclose(out, 0.25), "and the block still played"


def test_a_block_of_another_size_is_silence_and_counted() -> None:
    project, store = arrangement(0.25)
    engine, _ = playing(project, store)
    out = np.ones((BLOCK // 2, 2), dtype=np.float32)
    engine.callback(out, BLOCK // 2, None, Status())
    assert not out.any() and engine.xruns == 1 and engine.playhead == 0


# --------------------------------------------------------------------------- #
# the transport
# --------------------------------------------------------------------------- #


def numbered_arrangement() -> tuple[Project, dict[str, Decoded]]:
    project, store = arrangement(0.0)
    store["m-00000000"] = Decoded(numbered(), 48_000)
    return project, store


def test_a_stopped_engine_holds_its_playhead_and_plays_no_clip() -> None:
    project, store = arrangement(0.5)
    engine = Engine(BLOCK)
    engine.install(snapshot(project, store))
    assert not block(engine).any() and engine.playhead == 0
    engine.seek(1_000)
    block(engine)
    assert engine.playhead == 1_000 and not engine.playing

    engine.set_playing(True)
    assert np.allclose(block(engine), 0.5) and engine.playhead == 1_000 + BLOCK
    engine.set_playing(False)
    assert not block(engine).any() and engine.playhead == 1_000 + BLOCK


def test_a_gain_changed_while_stopped_is_in_place_when_playing_starts() -> None:
    project, store = arrangement(1.0)
    engine = Engine(BLOCK)
    snap = snapshot(project, store)
    engine.install(snap)
    block(engine)
    engine.send_gain(snap.generation, 0, 0.5)
    block(engine)
    engine.set_playing(True)
    assert np.allclose(block(engine), 0.5), "not ramped from 1 on the first block"


def looped(size: int, start: int, length: int, blocks: int) -> Audio:
    project, store = numbered_arrangement()
    engine = Engine(size)
    engine.install(snapshot(project, store))
    engine.set_loop(start, start + length, True)
    engine.seek(start)
    engine.set_playing(True)
    out = np.zeros((size, 2), dtype=np.float32)
    heard = []
    for _ in range(blocks):
        engine.process(out)
        heard.append(out[:, 0].copy())
    return np.concatenate(heard)


@pytest.mark.parametrize("size", [256, 512, 2048])
@pytest.mark.parametrize("length", [100, 3_000])
def test_a_loop_runs_to_its_end_and_on_from_its_start(size: int, length: int) -> None:
    """No gap and no repeated sample at the join, whatever the block, and
    with a loop shorter than a block, which wraps inside it more than once."""
    heard = looped(size, 5_000, length, 8)
    passage = numbered()[5_000 : 5_000 + length, 0]
    repeats = -(-heard.shape[0] // length)
    assert np.array_equal(heard, np.tile(passage, repeats)[: heard.shape[0]])


def test_a_playhead_before_the_loop_plays_into_it_and_then_loops() -> None:
    project, store = numbered_arrangement()
    engine = Engine(BLOCK)
    engine.install(snapshot(project, store))
    engine.set_loop(1_000, 1_300, True)
    engine.set_playing(True)
    heard = np.concatenate([block(engine)[:, 0] for _ in range(8)])
    expected = np.concatenate(
        [numbered()[:1_300, 0], np.tile(numbered()[1_000:1_300, 0], 3)]
    )[: heard.shape[0]]
    assert np.array_equal(heard, expected)


def test_a_playhead_past_the_loop_plays_on() -> None:
    project, store = numbered_arrangement()
    engine = Engine(BLOCK)
    engine.install(snapshot(project, store))
    engine.set_loop(1_000, 2_000, True)
    engine.seek(5_000)
    engine.set_playing(True)
    heard = np.concatenate([block(engine)[:, 0] for _ in range(4)])
    assert np.array_equal(heard, numbered()[5_000 : 5_000 + 4 * BLOCK, 0])


@pytest.mark.parametrize(
    ("start", "end", "on"), [(1_000, 1_063, True), (1_000, 2_000, False)]
)
def test_a_loop_too_short_or_switched_off_plays_through(
    start: int, end: int, on: bool
) -> None:
    project, store = numbered_arrangement()
    engine = Engine(BLOCK)
    engine.install(snapshot(project, store))
    engine.set_loop(start, end, on)
    engine.seek(start)
    engine.set_playing(True)
    heard = np.concatenate([block(engine)[:, 0] for _ in range(8)])
    assert np.array_equal(heard, numbered()[start : start + 8 * BLOCK, 0])


def test_a_gain_ramps_smoothly_across_a_block_the_loop_wraps() -> None:
    project, store = arrangement(1.0)
    engine, snap = playing(project, store)
    engine.set_loop(100, 300, True)
    block(engine)
    engine.send_gain(snap.generation, 0, 0.5)
    ramped = block(engine)[:, 0]
    assert ramped[-1] == pytest.approx(0.5)
    assert steps(ramped) <= 0.5 / BLOCK + 1e-6


# --------------------------------------------------------------------------- #
# the audition voice
# --------------------------------------------------------------------------- #


def test_a_voice_plays_from_its_first_frame_to_both_ears_then_silence() -> None:
    engine = Engine(BLOCK)
    sample = numbered(BLOCK + 10)
    engine.audition(Voice(sample))
    first, second = block(engine), block(engine)
    assert np.array_equal(first[:, 0], sample[:BLOCK, 0])
    assert np.array_equal(first[:, 1], sample[:BLOCK, 0])
    assert np.array_equal(second[:10, 0], sample[BLOCK:, 0])
    assert not second[10:].any() and not block(engine).any()


def test_a_stereo_voice_keeps_its_sides() -> None:
    engine = Engine(BLOCK)
    sample = np.ascontiguousarray(np.stack([numbered()[:, 0], -numbered()[:, 0]], 1))
    engine.audition(Voice(sample))
    out = block(engine)
    assert np.array_equal(out, sample[:BLOCK])


def test_the_next_voice_replaces_the_first_from_its_first_frame() -> None:
    engine = Engine(BLOCK)
    engine.audition(Voice(level(0.25)))
    block(engine)
    second = Voice(numbered())
    engine.audition(second)
    assert engine.holds_voice(second)
    assert np.array_equal(block(engine)[:, 0], numbered()[:BLOCK, 0])


def test_a_voice_is_heard_over_the_arrangement_and_under_no_channels_gain() -> None:
    project, store = arrangement(0.25)
    project.channels[0].mute = True
    engine, _ = playing(project, store)
    project.channels[0].mute = False
    engine.audition(Voice(level(0.125)))
    assert np.allclose(block(engine), 0.125), (
        "the muted channel is silent, the voice not"
    )

    playing_too, _ = playing(project, store)
    playing_too.audition(Voice(level(0.125)))
    assert np.allclose(block(playing_too), 0.375)


def test_the_engine_lets_go_of_a_voice_it_has_moved_past() -> None:
    engine = Engine(BLOCK)
    first = Voice(level(0.25))
    engine.audition(first)
    block(engine)
    engine.audition(Voice(level(0.5)))
    assert engine.holds_voice(first), "until the next block takes the new one up"
    block(engine)
    assert not engine.holds_voice(first)


def test_drain_applies_commands_with_no_stream_running() -> None:
    engine = Engine(BLOCK)
    engine.seek(4_000)
    engine.set_playing(True)
    engine.set_loop(0, 1_000, True)
    engine.drain()
    assert (engine.playhead, engine.playing) == (4_000, True)


def test_a_wrapped_block_is_silent_where_no_clip_plays() -> None:
    """A loop of 1000 over a clip that ends at 500: the piece of a wrapped
    block past the clip is silence, not what the rows held before."""
    project, store = numbered_arrangement()
    project.channels[0].clips[0].length = 500
    engine = Engine(BLOCK)
    engine.install(snapshot(project, store))
    engine.set_loop(0, 1_000, True)
    engine.set_playing(True)
    heard = np.concatenate([block(engine)[:, 0] for _ in range(8)])
    passage = np.concatenate([numbered()[:500, 0], np.zeros(500, np.float32)])
    # The clip keeps its file's start, so only its cut end fades (D-42).
    passage[500 - 32 : 500] = heard[500 - 32 : 500]
    assert np.array_equal(heard, np.tile(passage, 3)[: heard.shape[0]])


def test_a_gain_sent_before_the_stream_opens_reaches_the_snapshot_waiting() -> None:
    """A mute made before the first Play: drained with no stream running, it
    must land on the snapshot the engine has not taken up yet."""
    project, store = arrangement(0.5)
    engine = Engine(BLOCK)
    waiting = snapshot(project, store)
    engine.install(waiting)
    engine.send_gain(waiting.generation, 0, 0.0)
    engine.drain()
    engine.set_playing(True)
    assert not block(engine).any()
