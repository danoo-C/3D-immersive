"""The spatial path: each non-bypassed channel heard from where it is (05,
*Per-block processing*).

A `Space` is built on the UI thread for one snapshot. It holds the bank,
the distance settings and every buffer a block writes, sized to the
snapshot's spatial channels and the bank's `nfft`, so `render` makes no
array (D-106). Per block, for each spatial channel:

1. its **mono point** (D-16) has already been written into `src` by the
   engine, after the channel's gain;
2. **distance** (D-21): `(ref / max(r, min)) ** rolloff`, ramped across the
   block from the last block's value - or, keeping the level as mixed, never
   above 1: `(ref / max(r, ref)) ** rolloff` (D-131). The channel's meter is
   read here, before the HRTF (D-117);
3. **its filter**: the direction weighed by the lookup, the three nearest
   measurements' spectra blended per ear, and the far ear delayed by the
   blended ITD as a phase ramp, so both delays are non-negative (05).
   Keeping the level as mixed, each measurement is scaled as it is blended
   by the gain that makes it as loud as straight ahead; the ITD is blended
   with the plain weights, so where it is heard from does not move (D-131).
   Inside the minimum distance the filter fades towards flat and the ITD
   towards none, so at the listener's own position the channel is heard as
   it is (D-130);
4. **a pair** (D-132): a channel placed as two sources is two slots, its
   left side and its right, each placed as above. In the centre each fades
   to its own ear (D-134), and the two share a gain that keeps the pair as
   loud as its stem at any separation (D-133);
5. **the crossfade** (D-37): the source windowed twice - fading out against
   last block's filter, in against this block's.

Then every channel's two copies go through one batched `rfft`. The products
are summed over channels in the frequency domain, per ear, and two `irfft`s
and an overlap-add accumulator give the block. That keeps the inverse cost
the same for one channel or thirty-two.

**Compiled, and without the GIL** (D-138). All of the above is `_render`,
one numba kernel that releases the GIL for its whole run, where the numpy
it replaces waited for the GIL again at every call (D-137). It is that
Python, rewritten as loops in the same order and the same float32
arithmetic, and the tests hold it to it (`tests/reference_spatial.py`). The
FFTs are pocketfft's, through rocket-fft, into arrays made here. Every
array it takes is C-contiguous and of one dtype, and every flag a Python
bool, so it has one compiled signature (D-139).

**Float32 and complex64, `norm="ortho"`, contiguous, one dtype** (D-122).
The default norm hands numpy's FFT an integer factor that selects its
float64 loop and casts the batch through temporaries. `"ortho"` scales both
ways by 1/sqrt(n), which cancel, so the convolution with the bank's
unscaled spectra is exact. Each ear's filters are their own `[S, bins]`
array, and the windowed copies are ordered all fading-out then all
fading-in, so each half is one contiguous block of rows: numpy buffers,
and so allocates, for strided or mixed operands.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
from rocket_fft import c2r, r2c

from immersive.audio.compiled import kernel
from immersive.audio.dsp import ramp_steps
from immersive.audio.hrtf.bank import Bank
from immersive.audio.hrtf.lookup import Lookup, locate
from immersive.core.io.loudness import pink_weights
from immersive.core.model import Distance

#: The direction given a source at the listener's own position. It is heard
#: from nowhere there - the centre has faded it to flat (D-130) - but the
#: lookup needs a direction to weigh.
AHEAD: Final = (0.0, 1.0, 0.0)

#: A pair's two sides at equal power, when the level is not kept (D-133).
HALF_POWER: Final = 1.0 / math.sqrt(2.0)
#: The most a pair's gain rises, for sides that would all but cancel.
PAIR_CAP: Final = 2.0

#: What a source is: a channel's one point, or a pair's left or right side.
POINT: Final = -1

Samples = npt.NDArray[np.float32]
Spectra = npt.NDArray[np.complex64]
Floats = npt.NDArray[np.float64]
Indices = npt.NDArray[np.int64]

#: What `_render` takes after a block's positions, meters, bus and its two
#: switches: `Space.arguments`, in `_render`'s order.
Arguments = tuple[
    Indices,
    Indices,
    Indices,
    Spectra,
    Spectra,
    Spectra,
    float,
    float,
    float,
    bool,
    Indices,
    Floats,
    Indices,
    Indices,
    Indices,
    int,
    Floats,
    Floats,
    Spectra,
    Samples,
    Samples,
    Spectra,
    Spectra,
    Spectra,
    Spectra,
    Spectra,
    Spectra,
    Samples,
    Samples,
    Indices,
    Floats,
    Floats,
    Floats,
    Floats,
    Floats,
    Floats,
    Samples,
    Samples,
    Samples,
    Samples,
    Spectra,
    Indices,
]

#: A pair's left, right and shared spectra at the bank's bins, divided by
#: the stem as mixed (D-133).
Weighed = tuple[
    npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.complex128]
]


@dataclass(eq=False)
class Space:
    """One snapshot's spatial channels, and everything a block writes."""

    bank: Bank
    #: Each source's channel, its index among the snapshot's lanes, and which
    #: of it it is: `POINT`, or a pair's side, 0 left and 1 right (D-132).
    channels: tuple[int, ...]
    sides: tuple[int, ...]
    #: Each pair's two slots, and its stem's own spectra to read its loudness
    #: by (D-133): the left's and the right's square roots, and twice the
    #: shared spectrum's conjugate, `[pairs, bins]`.
    pairs: tuple[tuple[int, int], ...]
    pair_left: Spectra
    pair_right: Spectra
    pair_shared: Spectra
    rolloff: float
    min_distance: float
    ref_distance: float
    block: int
    #: `[S, block]` each source's signal - a channel's mono point, or a pair's
    #: side - written by the engine.
    src: Samples
    #: `[2S, nfft]` fading-out copies, then fading-in; zero past `block`.
    windowed: Samples
    #: `[2S, bins]` their spectra.
    spectra: Spectra
    #: `[S, bins]` this block's filters, and last block's, per ear.
    left: Spectra
    right: Spectra
    previous_left: Spectra
    previous_right: Spectra
    product: Spectra
    #: `[2, bins]` the sum over channels, and one half of it.
    total: Spectra
    half: Spectra
    #: `[2, nfft]` the block's inverse, and the overlap-add accumulator.
    inverse: Samples
    tail: Samples
    shifted: Samples
    #: The lookup's outputs, and each channel's ITD.
    vertices: npt.NDArray[np.int64]
    weights: npt.NDArray[np.float64]
    itds: npt.NDArray[np.float64]
    #: Each source's gain as the last block ended, and this block's target:
    #: its distance, and a pair's share (D-133).
    distance: npt.NDArray[np.float64]
    target: npt.NDArray[np.float64]
    #: Each channel's reach out of the centre this block: 0 at the listener,
    #: 1 at the minimum distance and beyond (D-130).
    reach: npt.NDArray[np.float64]
    #: The lookup's weights, scaled by each measurement's evening gain when
    #: the level is kept (D-131).
    loudness: npt.NDArray[np.float64]
    #: The crossfade's windows, and the gain ramp's steps.
    fade_in: Samples
    fade_out: Samples
    steps: Samples
    #: The ITD's phase ramp: bin numbers, and the ramp.
    bins_: Samples
    delay: Spectra
    #: What the kernel reads the tuples above as (D-139): each source's
    #: channel and side, and each pair's two slots, `[P, 2]`.
    of_channel: Indices
    of_side: Indices
    pair_slots: Indices
    #: The bank's arrays the kernel reads, each C-contiguous in its one
    #: dtype, and each measurement's evening gain, or 1 where a bank has
    #: none.
    itd: Floats
    filters: Spectra
    gains: Floats
    #: The axis the FFTs run along, as pocketfft takes it.
    axes: Indices
    #: Level as mixed (D-131): no boost nearer than the reference distance,
    #: and every direction as loud as the front.
    keep_level: bool = False
    #: The first block after a seek or a swap crossfades from nothing stale.
    fresh: bool = True
    #: Off only in a test: this block's filter on both halves, which is the
    #: uncrossfaded engine the roadmap's A/B listens against (D-37).
    crossfade: bool = True

    @property
    def count(self) -> int:
        return len(self.channels)

    @classmethod
    def build(
        cls,
        bank: Bank,
        channels: tuple[int, ...],
        positions: npt.NDArray[np.float64],
        distance: Distance,
        sides: tuple[int, ...] | None = None,
        spectra: Sequence[Weighed] | None = None,
    ) -> Space:
        """On the UI thread: every buffer, sized once. `sides` says which of
        its channel each source is, `POINT` by default; a pair's two sides
        are next to each other, and `spectra` has each pair's stem's own,
        unrelated pink noise when it is not given."""
        count = len(channels)
        kinds = sides if sides is not None else (POINT,) * count
        pairs = tuple((slot, slot + 1) for slot in range(count) if kinds[slot] == 0)
        bins = bank.nfft // 2 + 1
        if spectra is None:
            pink = pink_weights(bank.nfft)
            half = pink / (2.0 * pink.sum())
            spectra = [(half, half, np.zeros(bins, dtype=np.complex128))] * len(pairs)
        heard = list(spectra)
        block, nfft = bank.block, bank.nfft
        bins = nfft // 2 + 1
        steps = ramp_steps(block)
        directions = len(bank.itd)
        evening = (
            bank.evening if bank.evening.size == directions else np.ones(directions)
        )
        space = cls(
            bank=bank,
            channels=channels,
            sides=kinds,
            pairs=pairs,
            pair_left=np.array(
                [np.sqrt(left) for left, _, _ in heard], dtype=np.complex64
            ).reshape(len(pairs), bins),
            pair_right=np.array(
                [np.sqrt(right) for _, right, _ in heard], dtype=np.complex64
            ).reshape(len(pairs), bins),
            pair_shared=np.array(
                [2.0 * np.conj(shared) for _, _, shared in heard], dtype=np.complex64
            ).reshape(len(pairs), bins),
            rolloff=float(distance.rolloff),
            min_distance=float(distance.min_distance),
            ref_distance=float(distance.ref_distance),
            block=int(block),
            src=np.zeros((count, block), dtype=np.float32),
            windowed=np.zeros((2 * count, nfft), dtype=np.float32),
            spectra=np.zeros((2 * count, bins), dtype=np.complex64),
            left=np.zeros((count, bins), dtype=np.complex64),
            right=np.zeros((count, bins), dtype=np.complex64),
            previous_left=np.zeros((count, bins), dtype=np.complex64),
            previous_right=np.zeros((count, bins), dtype=np.complex64),
            product=np.zeros((count, bins), dtype=np.complex64),
            total=np.zeros((2, bins), dtype=np.complex64),
            half=np.zeros(bins, dtype=np.complex64),
            inverse=np.zeros((2, nfft), dtype=np.float32),
            tail=np.zeros((2, nfft), dtype=np.float32),
            shifted=np.zeros((2, nfft), dtype=np.float32),
            vertices=np.zeros((count, 3), dtype=np.int64),
            weights=np.zeros((count, 3)),
            itds=np.zeros(count),
            distance=np.zeros(count),
            target=np.zeros(count),
            reach=np.ones(count),
            loudness=np.zeros((count, 3)),
            keep_level=bool(distance.keep_level),
            fade_in=np.linspace(0.0, 1.0, block, dtype=np.float32),
            fade_out=np.linspace(1.0, 0.0, block, dtype=np.float32),
            steps=np.require(steps, np.float32, ("C", "W")),
            bins_=np.arange(bins, dtype=np.float32),
            delay=np.zeros(bins, dtype=np.complex64),
            of_channel=np.array(channels, dtype=np.int64),
            of_side=np.array(kinds, dtype=np.int64),
            pair_slots=np.array(pairs, dtype=np.int64).reshape(len(pairs), 2),
            itd=np.require(bank.itd, np.float64, ("C", "W")),
            filters=np.require(bank.filters, np.complex64, ("C", "W")),
            gains=np.require(evening, np.float64, ("C", "W")),
            axes=np.ones(1, dtype=np.int64),
        )
        return space

    # ------------------------------------------------------------ a block

    @property
    def arguments(self) -> Arguments:
        """What `_render` takes after a block's positions, meters, bus and
        its two switches, in its order: every array made here, and the
        bank's. The engine's block kernel hands them on as one tuple."""
        lookup = self.bank.lookup
        return (
            self.of_channel,
            self.of_side,
            self.pair_slots,
            self.pair_left,
            self.pair_right,
            self.pair_shared,
            self.rolloff,
            self.min_distance,
            self.ref_distance,
            self.keep_level,
            lookup.faces,
            lookup.inverses,
            lookup.neighbours,
            lookup.cells,
            lookup.offsets,
            lookup.resolution,
            self.itd,
            self.gains,
            self.filters,
            self.src,
            self.windowed,
            self.spectra,
            self.left,
            self.right,
            self.previous_left,
            self.previous_right,
            self.total,
            self.inverse,
            self.tail,
            self.vertices,
            self.weights,
            self.itds,
            self.distance,
            self.target,
            self.reach,
            self.loudness,
            self.fade_in,
            self.fade_out,
            self.steps,
            self.bins_,
            self.delay,
            self.axes,
        )

    def render(
        self,
        positions: npt.NDArray[np.float64],
        peaks: npt.NDArray[np.float64],
        bus_l: Samples,
        bus_r: Samples,
    ) -> None:
        """Every source's `src`, placed, summed into the bus: `_render`,
        with the GIL released for all of it (D-138). The engine calls the
        kernel from its own; this is for anything else that plays a space."""
        _render(
            positions, peaks, bus_l, bus_r, self.fresh, self.crossfade, *self.arguments
        )
        # The first block after a seek or a swap is fresh in its filters;
        # every block after it crossfades from the last.
        self.fresh = False

    def drain(self, bus_l: Samples, bus_r: Samples) -> None:
        """The accumulator's next block into the bus, and the rest moved up
        a block: what a stopped transport still does, so a pause decays
        rather than cuts, and a resume does not replay it."""
        _drain(self.tail, bus_l, bus_r)


def nothing(block: int) -> Space:
    """A space of no sources, made from an empty bank: what the engine's
    block kernel is handed when a snapshot has no space, so that it sees
    arrays of the same kinds either way and has one signature (D-141)."""
    made = _nothing.get(block)
    if made is None:
        lookup = Lookup.assemble(
            np.zeros((0, 3), dtype=np.int64),
            np.zeros((0, 3, 3)),
            np.zeros((0, 3), dtype=np.int64),
            np.zeros(0, dtype=np.int64),
            np.zeros(7, dtype=np.int64),
            1,
        )
        bank = Bank(
            title="",
            hash="",
            block=block,
            nfft=block,
            taps=0,
            max_itd=0.0,
            directions=np.zeros((0, 3)),
            lookup=lookup,
            itd=np.zeros(0),
            filters=np.zeros((0, 2, block // 2 + 1), dtype=np.complex64),
        )
        made = _nothing[block] = Space.build(bank, (), np.zeros((0, 2, 3)), Distance())
    return made


_nothing: dict[int, Space] = {}

# --------------------------------------------------------------- the kernel


@kernel
def _render(
    positions: Floats,
    peaks: Floats,
    bus_l: Samples,
    bus_r: Samples,
    fresh: bool,
    crossfade: bool,
    of_channel: Indices,
    of_side: Indices,
    pair_slots: Indices,
    pair_left: Spectra,
    pair_right: Spectra,
    pair_shared: Spectra,
    rolloff: float,
    min_distance: float,
    ref_distance: float,
    keep_level: bool,
    faces: Indices,
    inverses: Floats,
    neighbours: Indices,
    cells: Indices,
    offsets: Indices,
    resolution: int,
    itd: Floats,
    gains: Floats,
    filters: Spectra,
    src: Samples,
    windowed: Samples,
    spectra: Spectra,
    left: Spectra,
    right: Spectra,
    previous_left: Spectra,
    previous_right: Spectra,
    total: Spectra,
    inverse: Samples,
    tail: Samples,
    vertices: Indices,
    weights: Floats,
    itds: Floats,
    distance: Floats,
    target: Floats,
    reach: Floats,
    loudness: Floats,
    fade_in: Samples,
    fade_out: Samples,
    steps: Samples,
    bins_: Samples,
    delay: Spectra,
    axes: Indices,
) -> None:
    """A block of the spatial path, in the order the module's docstring
    gives, without the GIL."""
    count = of_channel.shape[0]
    block = src.shape[1]
    nfft = windowed.shape[1]
    bins = left.shape[1]

    # 1. Where each source is: its direction, weighed; its distance gain;
    # how far out of the centre it is; its ITD.
    for slot in range(count):
        side = of_side[slot] if of_side[slot] > 0 else 0
        x = positions[of_channel[slot], side, 0]
        y = positions[of_channel[slot], side, 1]
        z = positions[of_channel[slot], side, 2]
        r = math.sqrt(x * x + y * y + z * z)
        if r == 0.0:
            dx, dy, dz = AHEAD
        else:
            dx, dy, dz = x / r, y / r, z / r
        nearest = min_distance
        if keep_level:
            nearest = max(nearest, ref_distance)  # never above 1 (D-131)
        target[slot] = (ref_distance / max(r, nearest)) ** rolloff
        reach[slot] = min(r / min_distance, 1.0) if min_distance > 0.0 else 1.0
        face, a, b, c = locate(
            faces, inverses, neighbours, cells, offsets, resolution, dx, dy, dz
        )
        weight = a + b + c
        for corner, share in enumerate((a, b, c)):
            vertex = faces[face, corner]
            vertices[slot, corner] = vertex
            weights[slot, corner] = share / weight
        itds[slot] = (
            weights[slot, 0] * itd[vertices[slot, 0]]
            + weights[slot, 1] * itd[vertices[slot, 1]]
            + weights[slot, 2] * itd[vertices[slot, 2]]
        )
        for corner in range(3):
            loudness[slot, corner] = (
                weights[slot, corner] * gains[vertices[slot, corner]]
                if keep_level
                else weights[slot, corner]
            )

    # 2. Each source's filters, and a pair's share of the gain.
    for slot in range(count):
        _filter(
            slot,
            of_side[slot],
            filters,
            vertices,
            loudness,
            reach[slot],
            itds[slot],
            left[slot],
            right[slot],
            bins_,
            nfft,
            delay,
        )
    for pair in range(pair_slots.shape[0]):
        first, second = pair_slots[pair, 0], pair_slots[pair, 1]
        if keep_level:
            share = _pair_gain(
                left[first],
                right[first],
                left[second],
                right[second],
                pair_left[pair],
                pair_right[pair],
                pair_shared[pair],
            )
        else:
            share = HALF_POWER
        target[first] *= share
        target[second] *= share

    # 3. The gains onto the rows, ramped from the last block's; the meters.
    for slot in range(count):
        row = src[slot]
        gain = target[slot]
        level = gain if fresh else distance[slot]
        if level != gain:
            rise = np.float32(gain - level)
            start = np.float32(level)
            for i in range(block):
                row[i] = row[i] * (steps[i] * rise + start)
        elif gain != 1.0:
            scale = np.float32(gain)
            for i in range(block):
                row[i] = row[i] * scale
        distance[slot] = gain
        loudest = np.float32(0.0)
        for i in range(block):
            loudest = max(loudest, abs(row[i]))
        channel, side = of_channel[slot], of_side[slot]
        for which in range(2):
            if side != POINT and side != which:
                continue  # a pair's side is its own meter
            if loudest > peaks[channel, which]:
                peaks[channel, which] = loudest

    # 4. The crossfade: fading out against last block's filters, in against
    # this block's; one transform for all, summed over sources per ear.
    if fresh or not crossfade:
        _copy(left, previous_left)
        _copy(right, previous_right)
    for slot in range(count):
        for i in range(block):
            windowed[slot, i] = src[slot, i] * fade_out[i]
            windowed[count + slot, i] = src[slot, i] * fade_in[i]
    scale = np.float32(1.0 / math.sqrt(nfft))  # "ortho", both ways (D-122)
    r2c(windowed, spectra, axes, np.bool_(True), scale, np.int64(1))
    for ear in range(2):
        was = previous_left if ear == 0 else previous_right
        now = left if ear == 0 else right
        for k in range(bins):
            out = np.complex64(0.0)
            for slot in range(count):
                out += spectra[slot, k] * was[slot, k]
            into = np.complex64(0.0)
            for slot in range(count):
                into += spectra[count + slot, k] * now[slot, k]
            total[ear, k] = out + into
    c2r(total, inverse, axes, np.bool_(False), scale, np.int64(1))

    # 5. Overlap-add: the tail gains the block's inverse, gives its first
    # block to the bus, and moves up a block.
    for ear in range(2):
        for i in range(nfft):
            tail[ear, i] += inverse[ear, i]
    _drain(tail, bus_l, bus_r)
    _copy(left, previous_left)
    _copy(right, previous_right)


@kernel
def _filter(
    slot: int,
    own: int,
    filters: Spectra,
    vertices: Indices,
    loudness: Floats,
    reach: float,
    itd: float,
    left: Spectra,
    right: Spectra,
    bins_: Samples,
    nfft: int,
    delay: Spectra,
) -> None:
    """One source's filters: three measurements blended per ear, the far
    ear delayed by the ITD, and in the centre, faded towards flat (D-130),
    to its own ear for a pair's side (D-134)."""
    bins = left.shape[0]
    first, second, third = vertices[slot, 0], vertices[slot, 1], vertices[slot, 2]
    one = np.float32(loudness[slot, 0])
    two = np.float32(loudness[slot, 1])
    three = np.float32(loudness[slot, 2])
    near = np.float32(reach)
    for ear in range(2):
        out = left if ear == 0 else right
        a, b, c = filters[first, ear], filters[second, ear], filters[third, ear]
        for k in range(bins):
            value = a[k] * one
            value = value + b[k] * two
            value = value + c[k] * three
            if reach < 1.0:
                value = value * near
            out[k] = value
    itd = itd * reach
    # Positive: the left ear is the later, far one (phase 2).
    far_left = itd > 0.0
    if itd != 0.0:
        _delay(bins_, nfft, abs(itd), delay)
        far = left if far_left else right
        for k in range(bins):
            far[k] = far[k] * delay[k]
    if reach < 1.0:
        # The rest of the way to flat; its share of the delay to the
        # nearest whole sample, as the Python render explains (D-130).
        flat = np.float32(1.0 - reach)
        whole = round(abs(itd))
        for ear in range(2):
            if own != POINT and own != ear:
                continue
            row = left if ear == 0 else right
            if (far_left if ear == 0 else not far_left) and whole != 0:
                _delay(bins_, nfft, whole, delay)
                for k in range(bins):
                    row[k] = row[k] + delay[k] * flat
            else:
                for k in range(bins):
                    row[k] = row[k] + flat


@kernel
def _pair_gain(
    first_left: Spectra,
    first_right: Spectra,
    second_left: Spectra,
    second_right: Spectra,
    own: Spectra,
    other: Spectra,
    shared: Spectra,
) -> float:
    """A pair's share of the gain (D-133): `1 / sqrt(loudness)`, its
    loudness read with its stem's own spectra, relative to the stem."""
    loud = 0.0
    for k in range(first_left.shape[0]):
        for value in (
            first_left[k] * own[k],
            first_right[k] * own[k],
            second_left[k] * other[k],
            second_right[k] * other[k],
        ):
            loud += value.real * value.real + value.imag * value.imag
        cross = first_left[k] * np.conj(second_left[k]) + first_right[k] * np.conj(
            second_right[k]
        )
        loud += (np.conj(shared[k]) * cross).real
    return PAIR_CAP if loud <= 1.0 / PAIR_CAP**2 else 1.0 / math.sqrt(loud)


@kernel
def _drain(tail: Samples, bus_l: Samples, bus_r: Samples) -> None:
    """The tail's next block into the bus, and the rest moved up a block."""
    block = bus_l.shape[0]
    nfft = tail.shape[1]
    keep = nfft - block
    for i in range(block):
        bus_l[i] += tail[0, i]
        bus_r[i] += tail[1, i]
    for ear in range(2):
        for i in range(keep):
            tail[ear, i] = tail[ear, i + block]
        for i in range(keep, nfft):
            tail[ear, i] = 0.0


@kernel
def _copy(source: Spectra, into: Spectra) -> None:
    """`into[:] = source`, as a loop: a slice assignment needs numba's
    runtime, which kernels do without."""
    for row in range(source.shape[0]):
        for k in range(source.shape[1]):
            into[row, k] = source[row, k]


@kernel
def _delay(bins_: Samples, nfft: int, samples: float, out: Spectra) -> None:
    """`out`: a delay of `samples` as a phase ramp over the bins."""
    step = np.float32(-2.0 * math.pi * samples / nfft)
    for k in range(bins_.shape[0]):
        angle = bins_[k] * step
        out[k] = np.complex64(complex(np.cos(angle), np.sin(angle)))
