"""The spatial path, compiled (M4 phase 11, D-138): the kernel is the
Python render it replaced, to float32 rounding.

Each test plays one arrangement twice, through two engines built alike. One
renders through the kernel, as the application does. The other renders
through `reference_engine.process`, the Python block that played until
phase 10, whose space renders through `reference_spatial.render`.
They are compared block by block, what they send to the bus and what they
leave on the meters, while every source moves.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import numpy as np
import pytest

import reference_engine
from immersive.audio import engine as playing
from immersive.audio.engine import Engine, Voice
from immersive.audio.hrtf import lookup
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.audio.scheduler import Snapshot, build
from immersive.core.io.loudness import measure
from immersive.core.io.media import Decoded
from immersive.core.model import (
    Channel,
    Clip,
    MediaFile,
    Pairing,
    Placement,
    Position,
    Project,
)
from test_spatial import head

BLOCK = 256
FRAMES = 48_000
#: Float32 rounding, summed over a block's sources and a transform.
ROUNDING = 2e-6


@pytest.fixture(scope="module")
def bank() -> Iterator[Bank]:
    patch = pytest.MonkeyPatch()
    patch.setattr(lookup, "CELLS", 16)
    patch.setattr(lookup, "SAMPLES", 2)
    with tempfile.TemporaryDirectory() as cache:
        made = prepare(head(), BLOCK, Path(cache))
    patch.undo()
    assert isinstance(made, Bank)
    yield made


def stem(channels: int, seed: int) -> Decoded:
    """Noise at a mixed stem's level; a stereo one with its sides partly
    alike, and the spectra a pair's loudness is read from (D-133)."""
    rng = np.random.default_rng(seed)
    shared = rng.standard_normal(FRAMES)
    sides = [0.6 * shared + 0.4 * rng.standard_normal(FRAMES) for _ in range(channels)]
    audio = (0.1 * np.column_stack(sides)).astype(np.float32)
    audio.flags.writeable = False
    spectra = measure(audio) if channels == 2 else None
    fold = spectra.fold if spectra is not None else 1.0
    return Decoded(audio, 48_000, fold, spectra)


def arrangement(
    modes: list[Pairing], *, mono_pair: bool = False, keep_level: bool = True
) -> tuple[Project, dict[str, Decoded]]:
    """A channel for each mode: stereo stems, and with `mono_pair` a mono
    channel asking to be two sources (D-132)."""
    store: dict[str, Decoded] = {}
    project = Project()
    project.distance.keep_level = keep_level
    kinds = [(mode, 2) for mode in modes] + ([(Pairing.LINKED, 1)] if mono_pair else [])
    for n, (mode, sides) in enumerate(kinds):
        media = MediaFile(f"m-{n:08x}", f"/{n}.wav", f"{n}.wav", 48_000, sides, FRAMES)
        store[media.id] = stem(sides, n)
        project.media_pool.append(media)
        project.channels.append(
            Channel(
                f"c-{n:08x}",
                f"C{n}",
                "#A855F7",
                position=Position(1.0, 1.0, 0.0),
                placement=Placement(mode=mode, mono=sides == 1),
                clips=[Clip(f"k-{n:08x}", media.id, 0, 0, FRAMES)],
            )
        )
    return project, store


class Twins:
    """One arrangement in two engines: the kernel's, and the reference's."""

    def __init__(self, bank: Bank, project: Project, store: dict[str, Decoded]) -> None:
        self.bank, self.project, self.store = bank, project, store
        self.kernel = Engine(BLOCK)
        self.python = Engine(BLOCK)
        self.python.process = partial(reference_engine.process, self.python)  # type: ignore[method-assign]
        self.snapshots: list[Snapshot] = []
        self.install()
        for engine in (self.kernel, self.python):
            engine.set_playing(True)
        self.outs = [np.zeros((BLOCK, 2), dtype=np.float32) for _ in range(2)]
        self.block = 0

    def install(self) -> None:
        """A snapshot of the project for each."""
        made = []
        for engine in (self.kernel, self.python):
            snapshot = build(self.project, self.store.get, None, self.bank)
            engine.install(snapshot)
            made.append(snapshot)
        self.snapshots = made

    def spaces(self) -> list[object]:
        return [snapshot.space for snapshot in self.snapshots]

    def play(self, blocks: int) -> float:
        """`blocks` blocks, every source moved before each, the two compared
        block by block; the loudest sample heard."""
        loudest = 0.0
        for _ in range(blocks):
            for engine, snapshot in zip(
                (self.kernel, self.python), self.snapshots, strict=True
            ):
                move(engine, snapshot, self.project, self.block)
            for engine, out in zip((self.kernel, self.python), self.outs, strict=True):
                engine.process(out)
            kernel, python = self.outs
            np.testing.assert_allclose(kernel, python, atol=ROUNDING, rtol=0)
            np.testing.assert_allclose(
                self.snapshots[0].peaks, self.snapshots[1].peaks, atol=ROUNDING, rtol=0
            )
            loudest = max(loudest, float(np.abs(python).max()))
            self.block += 1
        return loudest


def move(engine: Engine, snapshot: Snapshot, project: Project, block: int) -> None:
    """Each channel round its own orbit, the first inside the centre, a
    pair's right side the other way round, higher."""
    for index in range(len(project.channels)):
        angle = index * 2.4 + block * 0.05
        reach = 0.1 if index == 0 else 1.0 + 0.3 * index
        x, y = reach * math.sin(angle), reach * math.cos(angle)
        engine.send_position(snapshot.generation, index, x, y, 0.2 * index)
        engine.send_position(snapshot.generation, index, -y, x, 0.5, 1)


def test_points_equal_the_reference(bank: Bank) -> None:
    project, store = arrangement([Pairing.POINT] * 5)
    twins = Twins(bank, project, store)

    assert twins.play(40) > 0.01, "something was heard"


def test_linked_and_free_pairs_equal_the_reference(bank: Bank) -> None:
    """With a pair inside the centre, where each side fades to its own ear
    (D-134), and a mono channel as two sources."""
    project, store = arrangement(
        [Pairing.LINKED, Pairing.FREE, Pairing.POINT, Pairing.FREE], mono_pair=True
    )
    twins = Twins(bank, project, store)

    assert twins.play(40) > 0.01


def test_level_as_mixed_off_equals_the_reference(bank: Bank) -> None:
    """D-21's law as it is, the set's own loudness by direction, and a pair
    at equal power."""
    project, store = arrangement(
        [Pairing.POINT, Pairing.LINKED, Pairing.FREE], keep_level=False
    )
    twins = Twins(bank, project, store)

    assert twins.play(30) > 0.01


def test_the_crossfade_off_equals_the_reference(bank: Bank) -> None:
    project, store = arrangement([Pairing.POINT, Pairing.LINKED])
    twins = Twins(bank, project, store)
    for space in twins.spaces():
        space.crossfade = False  # type: ignore[attr-defined]

    assert twins.play(20) > 0.01


def test_a_seek_and_a_swap_equal_the_reference(bank: Bank) -> None:
    """A seek starts the next block fresh; a new snapshot starts it fresh
    in its filters, and carries the gains across."""
    project, store = arrangement([Pairing.POINT, Pairing.LINKED, Pairing.FREE])
    twins = Twins(bank, project, store)
    twins.play(10)
    for engine in (twins.kernel, twins.python):
        engine.seek(20 * BLOCK)
    twins.play(10)
    project.distance.rolloff = 1.5
    twins.install()

    assert twins.play(10) > 0.01


def test_after_warming_no_arrangement_compiles_anything(bank: Bank) -> None:
    """One signature (D-139, D-141): what `warm` compiles is what every
    engine calls, with a space or without one, playing or stopped, with an
    audition or not, so no block on the audio thread compiles."""
    playing.warm()
    warmed = list(playing._block.signatures)  # type: ignore[attr-defined]
    for modes, keep_level, heard in (
        ([Pairing.POINT] * 3, True, bank),
        ([Pairing.LINKED, Pairing.FREE], True, bank),
        ([Pairing.POINT, Pairing.LINKED], False, bank),
        ([], True, bank),
        ([Pairing.POINT], True, None),
    ):
        project, store = arrangement(modes, mono_pair=not modes, keep_level=keep_level)
        engine = Engine(BLOCK)
        engine.install(build(project, store.get, None, heard))
        engine.audition(Voice(np.full((BLOCK * 2, 2), 0.1, dtype=np.float32)))
        out = np.zeros((BLOCK, 2), dtype=np.float32)
        engine.process(out)
        engine.set_playing(True)
        for _ in range(3):
            engine.process(out)

    assert len(warmed) == 1
    assert list(playing._block.signatures) == warmed  # type: ignore[attr-defined]
