"""Stereo placement (M4 phase 9; D-132 to D-135): a stereo channel as two
sources, free or linked in symmetry about a pivot. Headless.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.feed import Feed
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.io.media import Decoded
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Pairing,
    Placement,
    Position,
    Project,
    mirror,
    new_channel,
    paired,
    sides,
)
from test_feed import Counting, block

Audio = npt.NDArray[np.float32]
FRAMES = 48_000
AXES: list[tuple[bool, bool, bool]] = [
    (True, False, False),
    (False, True, False),
    (False, False, True),
    (True, True, False),
    (True, True, True),
    (False, False, False),
]


# --------------------------------------------------------------------------- #
# the model (D-132)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mirrored", AXES)
def test_the_mirror_inverts_what_is_mirrored_and_keeps_the_rest(
    mirrored: tuple[bool, bool, bool],
) -> None:
    left = Position(-1.5, 2.0, 0.5)
    right = mirror(left, Position(), mirrored)
    for axis, flipped in zip("xyz", mirrored, strict=True):
        was = getattr(left, axis)
        assert getattr(right, axis) == (-was if flipped else was)


@pytest.mark.parametrize("mirrored", AXES)
def test_the_mirror_is_about_the_pivot_and_its_own_inverse(
    mirrored: tuple[bool, bool, bool],
) -> None:
    """Moving either side of a linked pair finds the other the same way."""
    pivot = Position(0.7, 1.0, -0.2)
    left = Position(-0.3, 2.5, 0.4)
    right = mirror(left, pivot, mirrored)
    for axis, flipped in zip("xyz", mirrored, strict=True):
        centre, was = getattr(pivot, axis), getattr(left, axis)
        expected = 2 * centre - was if flipped else was
        assert getattr(right, axis) == pytest.approx(expected)
    back = mirror(right, pivot, mirrored)
    assert (back.x, back.y, back.z) == pytest.approx((left.x, left.y, left.z))


def a_channel(mode: Pairing, **placement: object) -> Channel:
    return Channel(
        "c-00000001",
        "C",
        "#A855F7",
        position=Position(-1.0, 2.0, 0.0),
        placement=Placement(mode=mode, **placement),  # type: ignore[arg-type]
    )


def test_a_free_pair_is_where_its_sides_were_put() -> None:
    channel = a_channel(Pairing.FREE, right=Position(3.0, -1.0, 1.0))
    assert sides(channel) == (Position(-1.0, 2.0, 0.0), Position(3.0, -1.0, 1.0))


def test_a_linked_pair_is_its_left_and_the_mirror_of_it() -> None:
    channel = a_channel(Pairing.LINKED, pivot=Position(0.5, 0.0, 0.0))
    assert sides(channel) == (Position(-1.0, 2.0, 0.0), Position(2.0, 2.0, 0.0))


def test_one_point_is_the_point_twice() -> None:
    channel = a_channel(Pairing.POINT, right=Position(9.0, 9.0, 9.0))
    assert sides(channel) == (channel.position, channel.position)


def stereo_and_mono() -> Project:
    return Project(
        media_pool=[
            MediaFile("m-00000001", "/s.wav", "s.wav", 48_000, 2, FRAMES),
            MediaFile("m-00000002", "/m.wav", "m.wav", 48_000, 1, FRAMES),
        ]
    )


@pytest.mark.parametrize(
    ("mode", "media", "mono", "is_pair"),
    [
        (Pairing.LINKED, "m-00000001", False, True),
        (Pairing.FREE, "m-00000001", False, True),
        (Pairing.POINT, "m-00000001", False, False),
        (Pairing.LINKED, "m-00000002", False, False),
        (Pairing.LINKED, "m-00000002", True, True),
        (Pairing.POINT, "m-00000002", True, False),
    ],
)
def test_a_channel_is_a_pair_when_its_mode_says_and_it_has_two_sides(
    mode: Pairing, media: str, mono: bool, is_pair: bool
) -> None:
    """A stereo clip, or a mono one asked to be two: a mono-only channel's
    fields stay one position until it asks."""
    project = stereo_and_mono()
    channel = a_channel(mode, mono=mono)
    channel.clips.append(Clip("k-00000001", media, 0, 0, FRAMES))
    project.channels.append(channel)
    assert paired(project, channel) is is_pair


def test_a_new_channel_is_a_linked_pair_mirroring_x_about_the_listener() -> None:
    channel = new_channel(Project(), ["#A855F7"])
    assert channel.placement == Placement(
        mode=Pairing.LINKED, pivot=Position(), mirrored=(True, False, False)
    )
    assert Channel("c-00000009", "Old", "#A855F7").placement.mode is Pairing.POINT


# --------------------------------------------------------------------------- #
# reaching the engine
# --------------------------------------------------------------------------- #


def fed_stereo() -> tuple[Document, Counting, Channel]:
    """One linked stereo channel through a feed, playing."""
    document = Document()
    store: dict[str, Decoded] = {}
    engine = Counting()
    engine.set_playing(True)
    feed = Feed(engine, store.get)
    document.observe(lambda: feed.update(document.project))
    media = MediaFile("m-00000001", "/s.wav", "s.wav", 48_000, 2, FRAMES)
    audio = np.full((FRAMES, 2), 0.25, dtype=np.float32)
    audio.flags.writeable = False
    store[media.id] = Decoded(audio, 48_000)
    document.push(AddMedia(document.project, [media]))
    channel = new_channel(document.project, ["#A855F7"])
    channel.position = Position(-1.0, 1.0, 0.0)  # off the listener: a mirror moves it
    document.push(AddChannel(document.project, channel))
    document.push(
        DropClips(
            document.project, channel, [Clip("k-00000001", media.id, 0, 0, FRAMES)]
        )
    )
    return document, engine, channel


@pytest.mark.parametrize(
    "edit",
    [
        ("position", Position(-2.0, 1.5, 0.0)),
        ("pivot", Position(0.5, 0.0, 0.0)),
        ("mirrored", (True, True, False)),
    ],
)
def test_moving_a_linked_pair_sends_positions_not_a_snapshot(
    edit: tuple[str, object],
) -> None:
    document, engine, channel = fed_stereo()
    installed, sent = len(engine.installed), engine.sent()
    name, value = edit
    target = channel if name == "position" else channel.placement
    document.push(SetAttribute(target, name, value))
    assert len(engine.installed) == installed and engine.sent() > sent
    block(engine)
    left, right = (
        engine.installed[-1].positions[0, 0].tolist(),
        engine.installed[-1].positions[0, 1].tolist(),
    )
    expected_left, expected_right = sides(channel)
    assert left == [expected_left.x, expected_left.y, expected_left.z]
    assert right == [expected_right.x, expected_right.y, expected_right.z]


def test_a_free_right_side_moves_on_its_own() -> None:
    document, engine, channel = fed_stereo()
    document.push(SetAttribute(channel.placement, "mode", Pairing.FREE))
    installed, sent = len(engine.installed), engine.sent()
    document.push(SetAttribute(channel.placement, "right", Position(2.0, 1.0, 0.5)))
    assert len(engine.installed) == installed and engine.sent() == sent + 1
    block(engine)
    assert engine.installed[-1].positions[0, 1].tolist() == [2.0, 1.0, 0.5]


def test_whether_a_channel_is_a_pair_is_a_snapshot() -> None:
    """It changes how many sources there are."""
    document, engine, channel = fed_stereo()
    installed = len(engine.installed)
    document.push(SetAttribute(channel.placement, "mode", Pairing.POINT))
    assert len(engine.installed) == installed + 1
    installed = len(engine.installed)
    document.push(SetAttribute(channel.placement, "mode", Pairing.FREE))
    assert len(engine.installed) == installed + 1
    installed = len(engine.installed)
    document.push(SetAttribute(channel.placement, "mode", Pairing.LINKED))
    assert len(engine.installed) == installed, "free to linked only moves a side"
