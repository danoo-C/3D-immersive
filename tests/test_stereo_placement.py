"""Stereo placement (M4 phase 9; D-132 to D-135): a stereo channel as two
sources, free or linked in symmetry about a pivot. Headless.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hearing import listen
from immersive.audio.engine import Engine
from immersive.audio.feed import Feed
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.audio.scheduler import build
from immersive.core.document import Document
from immersive.core.edits import AddChannel, AddMedia, DropClips, SetAttribute
from immersive.core.io.loudness import fold, weighted_power
from immersive.core.io.media import Decoded
from immersive.core.model import (
    Channel,
    Clip,
    Master,
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


# --------------------------------------------------------------------------- #
# the engine (D-133, D-134)
# --------------------------------------------------------------------------- #

BLOCK = 256


@pytest.fixture(scope="module")
def bank() -> Iterator[Bank]:
    from test_spatial import head

    patch = pytest.MonkeyPatch()
    patch.setattr(lookup, "CELLS", 16)
    patch.setattr(lookup, "SAMPLES", 2)
    with tempfile.TemporaryDirectory() as cache:
        made = prepare(head(), BLOCK, Path(cache))
        assert isinstance(made, Bank)
        yield made
    patch.undo()


def pink(seconds: float, seed: int) -> Audio:
    frames = int(seconds * 48_000)
    spectrum = np.fft.rfft(np.random.default_rng(seed).standard_normal(frames))
    frequencies = np.fft.rfftfreq(frames, 1 / 48_000)
    spectrum[1:] /= np.sqrt(frequencies[1:])
    spectrum[0] = 0.0
    noise = np.fft.irfft(spectrum, frames)
    return (0.1 * noise / noise.std()).astype(np.float32)


def stem(left: Audio, right: Audio) -> Decoded:
    audio = np.ascontiguousarray(np.column_stack([left, right]), dtype=np.float32)
    audio.flags.writeable = False
    return Decoded(audio, 48_000, fold(audio))


def heard_placed(
    bank: Bank,
    decoded: Decoded,
    placement: Placement,
    left: Position,
    **distance: object,
) -> Audio:
    frames = decoded.frames
    media = MediaFile("m-00000001", "/s.wav", "s.wav", 48_000, decoded.channels, frames)
    project = Project(
        media_pool=[media],
        master=Master(limiter_on=False),
        channels=[
            Channel(
                "c-00000001",
                "C",
                "#A855F7",
                position=left,
                placement=placement,
                clips=[Clip("k-00000001", media.id, 0, 0, frames)],
            )
        ],
    )
    for name, value in distance.items():
        setattr(project.distance, name, value)
    engine = Engine(BLOCK)
    engine.install(build(project, {media.id: decoded}.get, None, bank))
    engine.set_playing(True)
    return listen(engine, frames // BLOCK - 1)


def loudness(out: npt.NDArray[np.floating]) -> float:
    return 10 * math.log10(
        weighted_power(np.asarray(out[:, 0], np.float64))
        + weighted_power(np.asarray(out[:, 1], np.float64))
    )


def at(degrees: float) -> Position:
    """One metre out, `degrees` to the right of straight ahead."""
    return Position(
        math.sin(math.radians(degrees)), math.cos(math.radians(degrees)), 0.0
    )


def test_a_pair_at_the_listener_is_the_stem_as_mixed(bank: Bank) -> None:
    """Each side to its own ear (D-134): the default, heard as it was mixed."""
    decoded = stem(pink(1.0, 1), pink(1.0, 2))
    out = heard_placed(bank, decoded, Placement(mode=Pairing.LINKED), Position())
    np.testing.assert_allclose(out, decoded.audio[: len(out)], atol=1e-5)


@pytest.mark.parametrize("apart", [0.0, 30.0, 90.0, 180.0])
@pytest.mark.parametrize("kind", ["alike", "unrelated"])
def test_a_pair_is_as_loud_as_its_stem_at_any_separation(
    bank: Bank, apart: float, kind: str
) -> None:
    """Together a pair adds as one source and apart as two; its gain keeps it
    as loud as the stem as mixed either way (D-133)."""
    left = pink(2.0, 3)
    decoded = stem(left, left if kind == "alike" else pink(2.0, 4))
    placement = Placement(mode=Pairing.FREE, right=at(apart / 2))
    out = heard_placed(bank, decoded, placement, at(-apart / 2))
    frames = len(out)
    as_mixed = loudness(decoded.audio[:frames])
    assert loudness(out) - as_mixed == pytest.approx(0.0, abs=0.2)


def test_with_level_as_mixed_off_each_side_is_at_half_power(bank: Bank) -> None:
    """At the listener, with no distance law, only the pair's share is left."""
    decoded = stem(pink(1.0, 5), pink(1.0, 6))
    out = heard_placed(
        bank,
        decoded,
        Placement(mode=Pairing.LINKED),
        Position(),
        keep_level=False,
        rolloff=0.0,
    )
    np.testing.assert_allclose(out, decoded.audio[: len(out)] / math.sqrt(2), atol=1e-5)


def test_a_mono_channel_as_two_sources_is_heard_from_both_points(bank: Bank) -> None:
    mono = pink(1.0, 7)[:, None].copy()
    mono.flags.writeable = False
    decoded = Decoded(mono, 48_000)
    both = Placement(mode=Pairing.FREE, right=at(90.0), mono=True)
    at_listener = heard_placed(
        bank, decoded, Placement(mode=Pairing.LINKED, mono=True), Position()
    )
    np.testing.assert_allclose(
        at_listener[:, 0], mono[: len(at_listener), 0], atol=1e-5
    )
    np.testing.assert_allclose(
        at_listener[:, 1], mono[: len(at_listener), 0], atol=1e-5
    )
    apart = heard_placed(bank, decoded, both, at(-90.0))
    alone = heard_placed(bank, decoded, Placement(), at(-90.0))

    def lean(out: Audio) -> float:
        left, right = (
            weighted_power(np.asarray(out[:, s], np.float64)) for s in (0, 1)
        )
        return abs(10 * math.log10(left / right))

    assert lean(apart) < 0.5 < 2.0 < lean(alone), "from both sides, not one"


def test_each_side_is_heard_from_where_it_is(bank: Bank) -> None:
    """The stem's left alone, placed on the left and then on the right."""
    decoded = stem(pink(1.0, 8), np.zeros(48_000, dtype=np.float32))

    def ears(left: Position, right: Position) -> float:
        out = heard_placed(
            bank, decoded, Placement(mode=Pairing.FREE, right=right), left
        )
        powers = [weighted_power(np.asarray(out[:, s], np.float64)) for s in (0, 1)]
        return 10 * math.log10(powers[1] / powers[0])

    assert ears(at(-90.0), at(90.0)) < -1.0 < 1.0 < ears(at(90.0), at(-90.0))


def test_a_pairs_meters_read_its_two_sides(bank: Bank) -> None:
    frames = 4 * BLOCK
    audio = np.column_stack(
        [np.full(frames, 0.4, np.float32), np.full(frames, 0.1, np.float32)]
    )
    audio.flags.writeable = False
    decoded = Decoded(audio, 48_000, fold(audio))
    media = MediaFile("m-00000001", "/s.wav", "s.wav", 48_000, 2, frames)
    project = Project(
        media_pool=[media],
        channels=[
            Channel(
                "c-00000001",
                "C",
                "#A855F7",
                placement=Placement(mode=Pairing.LINKED),
                clips=[Clip("k-00000001", media.id, 0, 0, frames)],
            )
        ],
    )
    engine = Engine(BLOCK)
    engine.install(build(project, {media.id: decoded}.get, None, bank))
    engine.set_playing(True)
    engine.process(np.zeros((BLOCK, 2), dtype=np.float32))
    [(_, left, right)] = engine.take_channel_peaks()
    assert left == pytest.approx(0.4) and right == pytest.approx(0.1)
