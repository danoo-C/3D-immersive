"""The feed: the document watched from the UI thread, and the engine told a
snapshot for what plays and a command for how loud (D-105). No device, no
window - a `Document`, its edits, and the engine run block by block."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Callable

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.engine import RING, Engine
from immersive.audio.feed import Feed
from immersive.audio.scheduler import Snapshot
from immersive.core.commands import Command
from immersive.core.document import Document
from immersive.core.edits import (
    AddChannel,
    AddMedia,
    DropClips,
    Edge,
    MoveChannel,
    MoveClips,
    SetAttribute,
    SlipClips,
    TrimClips,
)
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, Fade, FadeShape, MediaFile, Project

Audio = npt.NDArray[np.float32]
BLOCK = 256
FRAMES = 48_000


class Counting(Engine):
    """An engine that says how often it was handed a snapshot."""

    def __init__(self) -> None:
        super().__init__(BLOCK)
        self.installed: list[Snapshot] = []

    def install(self, snapshot: Snapshot) -> None:
        self.installed.append(snapshot)
        super().install(snapshot)

    def sent(self) -> int:
        return self._written


def level(value: float) -> Decoded:
    audio = np.full((FRAMES, 1), value, dtype=np.float32)
    audio.flags.writeable = False
    return Decoded(audio, 48_000)


def fed(*values: float) -> tuple[Document, Counting, Feed, dict[str, Decoded]]:
    """A channel per value, each playing a whole sample of it from 0, with a
    feed following the document."""
    document = Document()
    store: dict[str, Decoded] = {}
    engine = Counting()
    feed = Feed(engine, store.get)
    document.observe(lambda: feed.update(document.project))
    for n, value in enumerate(values):
        media = MediaFile(f"m-0000000{n}", f"/{n}.wav", f"{n}.wav", 48_000, 1, FRAMES)
        store[media.id] = level(value)
        document.push(AddMedia(document.project, [media]))
        channel = Channel(f"c-0000000{n}", f"C{n}", "#A855F7")
        document.push(AddChannel(document.project, channel))
        clip = Clip(f"k-0000000{n}", media.id, 0, 0, FRAMES)
        document.push(DropClips(document.project, channel, [clip]))
    return document, engine, feed, store


def block(engine: Engine) -> Audio:
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    engine.process(out)
    return out


def settled(engine: Engine) -> Audio:
    """A block after any ramp has finished."""
    block(engine)
    return block(engine)


def test_a_structural_edit_hands_over_a_snapshot_and_no_command() -> None:
    document, engine, _, _ = fed(0.25)
    installed, sent = len(engine.installed), engine.sent()
    clip = document.project.channels[0].clips[0]

    document.push(MoveClips(document.project, [clip], 1_000))

    assert len(engine.installed) == installed + 1 and engine.sent() == sent
    assert engine.installed[-1].lanes[0].clips[0].start == 1_000


def first_clip(project: Project) -> Clip:
    return project.channels[0].clips[0]


STRUCTURAL: dict[str, Callable[[Project], Command]] = {
    "a move": lambda p: MoveClips(p, [first_clip(p)], 1_000),
    "a trim": lambda p: TrimClips(p, [first_clip(p)], Edge.END, -1_000),
    "a slip": lambda p: SlipClips(p, [first_clip(p)], 0),
    "a clip's gain": lambda p: SetAttribute(first_clip(p), "gain_db", -3.0),
    "a fade-in's length": lambda p: SetAttribute(first_clip(p), "fade_in", Fade(100)),
    "a fade-in's shape": lambda p: SetAttribute(
        first_clip(p), "fade_in", Fade(0, FadeShape.EQUAL_POWER)
    ),
    "a fade-out's length": lambda p: SetAttribute(first_clip(p), "fade_out", Fade(9)),
    "a fade-out's shape": lambda p: SetAttribute(
        first_clip(p), "fade_out", Fade(0, FadeShape.EQUAL_POWER)
    ),
    "a sample's length": lambda p: SetAttribute(p.media_pool[0], "frames", FRAMES + 1),
}


@pytest.mark.parametrize("edit", list(STRUCTURAL))
def test_every_edit_to_what_plays_hands_over_a_snapshot(edit: str) -> None:
    document, engine, _, _ = fed(0.25)
    if edit == "a slip":
        document.push(
            TrimClips(document.project, [first_clip(document.project)], Edge.START, 500)
        )
    installed = len(engine.installed)
    document.push(STRUCTURAL[edit](document.project))
    assert len(engine.installed) == installed + 1


def test_swapping_two_channels_that_play_alike_is_still_a_new_order() -> None:
    """Their clips are identical, so only the channels' ids tell the old
    order from the new - and a gain sent afterwards counts in the new."""
    document, engine, _, _ = fed(0.5, 0.5)
    first, second = document.project.channels
    document.push(SetAttribute(second.clips[0], "media_id", first.clips[0].media_id))
    document.push(SetAttribute(first, "gain_db", -120.0))
    installed = len(engine.installed)

    document.push(MoveChannel(document.project, second, 0))
    document.push(SetAttribute(first, "mute", True))

    assert len(engine.installed) == installed + 1
    assert np.allclose(settled(engine), 0.5)


def test_a_gain_edit_sends_a_command_and_no_snapshot() -> None:
    document, engine, _, _ = fed(0.5)
    installed, sent = len(engine.installed), engine.sent()

    document.push(SetAttribute(document.project.channels[0], "gain_db", -120.0))

    assert len(engine.installed) == installed and engine.sent() == sent + 1
    assert np.allclose(settled(engine), 0.5 * 10 ** (-120 / 20), atol=1e-9)


def test_undo_tells_the_engine_the_same_way() -> None:
    document, engine, _, _ = fed(0.5)
    channel = document.project.channels[0]
    document.push(SetAttribute(channel, "mute", True))
    document.push(MoveClips(document.project, [channel.clips[0]], 1_000))
    installed, sent = len(engine.installed), engine.sent()

    document.undo()
    assert len(engine.installed) == installed + 1 and engine.sent() == sent
    document.undo()
    assert len(engine.installed) == installed + 1 and engine.sent() == sent + 1
    assert np.allclose(settled(engine), 0.5)


def test_soloing_one_channel_sends_a_zero_to_every_other() -> None:
    document, engine, _, _ = fed(0.0625, 0.125, 0.25)
    sent = engine.sent()
    document.push(SetAttribute(document.project.channels[1], "solo", True))
    assert engine.sent() == sent + 2
    assert np.allclose(settled(engine), 0.125)


def test_a_sample_decoded_after_its_clip_was_placed_is_heard() -> None:
    """Opening a project places its clips before its samples are loaded."""
    document, engine, feed, store = fed(0.25)
    decoded = store.pop("m-00000000")
    feed.update(document.project)
    assert not settled(engine).any()

    store["m-00000000"] = decoded
    feed.update(document.project)

    assert np.allclose(settled(engine), 0.25)


def test_a_gain_after_a_reorder_lands_on_the_right_channel() -> None:
    document, engine, _, _ = fed(0.125, 0.25)
    quiet, loud = document.project.channels
    document.push(MoveChannel(document.project, loud, 0))
    block(engine)

    document.push(SetAttribute(quiet, "mute", True))

    assert np.allclose(settled(engine), 0.25)


def test_nothing_is_told_when_nothing_the_engine_plays_changed() -> None:
    document, engine, _, _ = fed(0.25)
    installed, sent = len(engine.installed), engine.sent()
    document.push(SetAttribute(document.project.channels[0], "name", "Kick"))
    document.push(SetAttribute(document.project, "bpm", 90.0))
    assert (len(engine.installed), engine.sent()) == (installed, sent)


def test_an_old_snapshot_is_freed_by_the_feed_and_never_by_the_engine() -> None:
    document, engine, feed, _ = fed(0.25)
    block(engine)
    first = engine.installed[-1]
    clip = document.project.channels[0].clips[0]
    document.push(MoveClips(document.project, [clip], 1_000))
    gone = weakref.ref(first)
    engine.installed.clear()
    del first

    block(engine)  # the engine moves past it
    gc.collect()
    assert gone() is not None, "still held on the UI thread"

    feed.release()
    gc.collect()
    assert gone() is None
    assert len(feed.held()) == 1


def test_a_full_ring_sends_the_gains_as_a_snapshot_instead() -> None:
    """Nothing drains the ring while nothing plays."""
    document, engine, _, _ = fed(0.5)
    for _ in range(RING - engine.sent()):
        engine.send_gain(0, 0, 1.0)
    installed = len(engine.installed)

    document.push(SetAttribute(document.project.channels[0], "mute", True))

    assert len(engine.installed) == installed + 1
    assert engine.installed[-1].targets.tolist() == [0.0]
