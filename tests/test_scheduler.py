"""What plays: the snapshot, and a channel's share of a block read out of it
(05, *Scheduler*; D-42). No device, no window."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from immersive.audio.dsp import IMPLICIT_FADE, db_to_gain, fade_in, fade_out
from immersive.audio.scheduler import Snapshot, build, empty, fill, gains
from immersive.core.io.media import Decoded
from immersive.core.model import Channel, Clip, Fade, FadeShape, MediaFile, Project

Audio = npt.NDArray[np.float32]
FRAMES = 20_000


def numbered(frames: int = FRAMES, channels: int = 1) -> Audio:
    """Every frame its own value, and the right side the left's negative, so
    a read from the wrong place or the wrong side shows."""
    values = (np.arange(frames, dtype=np.float32) + 1) / 65_536
    columns = [values, -values][:channels]
    audio = np.ascontiguousarray(np.stack(columns, axis=1), dtype=np.float32)
    audio.flags.writeable = False
    return audio


def arrangement(
    *lanes: list[Clip], frames: int = FRAMES, channels: int = 1, missing: bool = False
) -> tuple[Project, dict[str, Decoded]]:
    media = MediaFile("m-00000001", "/a.wav", "a.wav", 48_000, channels, frames)
    project = Project(
        media_pool=[media],
        channels=[
            Channel(f"c-0000000{n}", f"C{n}", "#A855F7", clips=list(clips))
            for n, clips in enumerate(lanes)
        ],
    )
    store = {} if missing else {media.id: Decoded(numbered(frames, channels), 48_000)}
    return project, store


def snapshot(project: Project, store: dict[str, Decoded]) -> Snapshot:
    return build(project, store.get)


def played(snap: Snapshot, lane: int, start: int, stop: int, block: int) -> Audio:
    """The lane read block by block from `start`, `(stop - start, 2)`."""
    out = np.zeros((stop - start, 2), dtype=np.float32)
    left = np.empty(block, dtype=np.float32)
    right = np.empty(block, dtype=np.float32)
    for t in range(start, stop, block):
        if fill(snap.lanes[lane], t, left, right):
            count = min(block, stop - t)
            out[t - start : t - start + count, 0] = left[:count]
            out[t - start : t - start + count, 1] = right[:count]
    return out


def clip(start: int, offset: int, length: int, **kwargs: object) -> Clip:
    return Clip("k-00000001", "m-00000001", start, offset, length, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# where a clip plays from
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("block", [256, 512, 2048])
def test_a_clip_plays_its_sample_from_offset_for_length_at_start(block: int) -> None:
    """Exact to the sample, across block boundaries: a clip starting
    mid-block, and ending mid-block several blocks on. The fades are what
    D-42 adds at the two edges away from the file's own, and are left out
    of what is compared."""
    placed = clip(start=1_000, offset=3_000, length=5_000)
    project, store = arrangement([placed])
    out = played(snapshot(project, store), 0, 0, 8_192, block)
    sample = numbered()

    inner = slice(1_000 + IMPLICIT_FADE, 6_000 - IMPLICIT_FADE)
    expected = sample[3_000 + IMPLICIT_FADE : 8_000 - IMPLICIT_FADE, 0]
    assert np.array_equal(out[inner, 0], expected)
    assert np.array_equal(out[inner, 1], expected), "mono to both ears"
    assert not out[:1_000].any() and not out[6_000:].any()
    assert out[1_000, 0] == 0.0, "the implicit fade-in starts silent"


def test_a_clip_inside_one_block_plays_whole() -> None:
    placed = clip(start=100, offset=0, length=200)
    project, store = arrangement([placed], frames=200)
    out = played(snapshot(project, store), 0, 0, 512, 512)
    assert np.array_equal(out[100:300, 0], numbered(200)[:, 0])
    assert not out[:100].any() and not out[300:].any()


def test_neighbouring_clips_meet_without_a_gap_or_an_overlap() -> None:
    head = clip(start=0, offset=0, length=700)
    tail = Clip("k-00000002", "m-00000001", 700, 700, 700)
    project, store = arrangement([head, tail], frames=1_400)
    out = played(snapshot(project, store), 0, 0, 1_536, 512)
    sample = numbered(1_400)[:, 0]
    # A split: the tail's head and the head's tail each fade over 32 samples.
    assert np.array_equal(out[: 700 - 32, 0], sample[: 700 - 32])
    assert np.array_equal(out[700 + 32 : 1_400, 0], sample[700 + 32 :])


def test_a_whole_sample_clip_at_zero_is_bit_transparent() -> None:
    """D-42's exemption: no gain, no fades, the file's own start and end."""
    for channels in (1, 2):
        placed = clip(start=0, offset=0, length=FRAMES)
        project, store = arrangement([placed], channels=channels)
        out = played(snapshot(project, store), 0, 0, FRAMES, 512)
        sample = numbered(channels=channels)
        assert out[:, 0].tobytes() == sample[:, 0].tobytes()
        assert out[:, 1].tobytes() == sample[:, channels - 1].tobytes()


def test_a_stereo_clip_keeps_its_sides() -> None:
    placed = clip(start=0, offset=0, length=FRAMES)
    project, store = arrangement([placed], channels=2)
    out = played(snapshot(project, store), 0, 0, 1_024, 256)
    assert (out[1:, 0] > 0).all() and (out[1:, 1] < 0).all()


def test_a_missing_sample_plays_silence_and_the_rest_plays() -> None:
    project, store = arrangement([clip(0, 0, FRAMES)], [clip(0, 0, FRAMES)])
    other = MediaFile("m-00000002", "/b.wav", "b.wav", 48_000, 1, FRAMES)
    project.media_pool.append(other)
    project.channels[1].clips[0] = Clip("k-00000002", other.id, 0, 0, FRAMES)
    snap = snapshot(project, store)
    assert not played(snap, 1, 0, 2_048, 512).any()
    assert played(snap, 0, 0, 2_048, 512).any()


def test_a_block_with_nothing_in_it_says_so() -> None:
    project, store = arrangement([clip(5_000, 0, 1_000)])
    left = np.full(512, np.nan, dtype=np.float32)
    right = left.copy()
    assert not fill(snapshot(project, store).lanes[0], 0, left, right)
    assert fill(snapshot(project, store).lanes[0], 4_800, left, right)
    assert not left[:200].any(), "silence before the clip, not what was there"


# --------------------------------------------------------------------------- #
# fades (D-42)
# --------------------------------------------------------------------------- #


def gains_of(out: Audio, start: int, offset: int, count: int) -> Audio:
    """What each sample of a mono clip was multiplied by."""
    return out[start : start + count, 0] / numbered()[offset : offset + count, 0]


def test_an_edge_away_from_its_files_own_fades_over_32_samples() -> None:
    placed = clip(start=0, offset=1_000, length=4_000)
    project, store = arrangement([placed])
    out = played(snapshot(project, store), 0, 0, 4_096, 512)
    head = gains_of(out, 0, 1_000, IMPLICIT_FADE)
    tail = gains_of(out, 4_000 - IMPLICIT_FADE, 5_000 - IMPLICIT_FADE, IMPLICIT_FADE)
    assert np.allclose(head, fade_in(FadeShape.LINEAR, IMPLICIT_FADE), atol=1e-6)
    assert np.allclose(tail, fade_out(FadeShape.LINEAR, IMPLICIT_FADE), atol=1e-6)
    assert out[IMPLICIT_FADE, 0] == numbered()[1_000 + IMPLICIT_FADE, 0], "then whole"


def test_the_files_own_start_and_end_get_no_implicit_fade() -> None:
    placed = clip(start=0, offset=0, length=FRAMES)
    project, store = arrangement([placed])
    snap = snapshot(project, store)
    assert snap.lanes[0].clips[0].head is None and snap.lanes[0].clips[0].tail is None


@pytest.mark.parametrize("shape", list(FadeShape))
def test_an_explicit_fade_replaces_the_implicit_one(shape: FadeShape) -> None:
    placed = clip(
        start=0,
        offset=1_000,
        length=4_000,
        fade_in=Fade(100, shape),
        fade_out=Fade(200, shape),
    )
    project, store = arrangement([placed])
    out = played(snapshot(project, store), 0, 0, 4_096, 256)
    assert np.allclose(gains_of(out, 0, 1_000, 100), fade_in(shape, 100), atol=1e-6)
    tail = gains_of(out, 3_800, 4_800, 200)
    assert np.allclose(tail, fade_out(shape, 200), atol=1e-6)
    assert gains_of(out, 100, 1_100, 1)[0] == 1.0, "not the implicit fade on top"


def test_an_implicit_fade_is_never_more_than_half_a_short_clip() -> None:
    placed = clip(start=0, offset=10, length=40)
    project, store = arrangement([placed])
    placed_ = snapshot(project, store).lanes[0].clips[0]
    assert placed_.head is not None and placed_.head.shape == (20,)
    assert placed_.tail is not None and placed_.tail.shape == (20,)


def test_a_fade_is_read_across_a_block_boundary() -> None:
    placed = clip(start=500, offset=0, length=3_000, fade_in=Fade(1_000))
    project, store = arrangement([placed])
    for block in (256, 512, 2048):
        out = played(snapshot(project, store), 0, 0, 4_096, block)
        applied = gains_of(out, 500, 0, 1_000)
        assert np.allclose(applied, fade_in(FadeShape.LINEAR, 1_000), atol=1e-6)


# --------------------------------------------------------------------------- #
# gain
# --------------------------------------------------------------------------- #


def test_clip_gain_applies_in_decibels() -> None:
    placed = clip(start=0, offset=0, length=FRAMES, gain_db=-6.0)
    project, store = arrangement([placed])
    out = played(snapshot(project, store), 0, 0, 1_024, 512)
    expected = numbered()[:1_024, 0] * np.float32(db_to_gain(-6.0))
    assert np.allclose(out[:, 0], expected)


def test_a_channels_gain_folds_in_mute_and_solo() -> None:
    project, _ = arrangement([], [], [], [])
    a, b, c, d = project.channels
    a.gain_db, b.solo, c.solo, c.mute = -6.0, True, True, True
    d.solo = False
    assert gains(project) == [0.0, 1.0, 0.0, 0.0]
    b.solo = False
    c.mute = False
    c.solo = False
    assert gains(project) == [pytest.approx(db_to_gain(-6.0)), 1.0, 1.0, 1.0]


# --------------------------------------------------------------------------- #
# the snapshot
# --------------------------------------------------------------------------- #


def test_a_snapshot_knows_its_generation_and_where_each_channel_was() -> None:
    project, store = arrangement([], [], [])
    first = build(project, store.get)
    project.channels.insert(0, project.channels.pop(2))
    project.channels.append(Channel("c-000000ff", "New", "#A855F7"))
    second = build(project, store.get, first)

    assert (first.generation, second.generation) == (1, 2)
    assert second.carry == (2, 0, 1, -1)
    assert second.levels.tolist() == second.targets.tolist() == [1.0] * 4
    assert empty().generation == 0 and empty().lanes == ()


def test_a_snapshot_shares_the_sessions_samples_rather_than_copying_them() -> None:
    project, store = arrangement([clip(0, 0, FRAMES)])
    placed = snapshot(project, store).lanes[0].clips[0]
    assert placed.audio is store["m-00000001"].audio
