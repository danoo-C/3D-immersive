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

from immersive.audio.dsp import ramp_steps
from immersive.audio.hrtf.bank import Bank
from immersive.audio.hrtf.lookup import Lookup
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
    #: The lookup's inputs and outputs, and each channel's ITD.
    directions: npt.NDArray[np.float64]
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
    #: The lookup's weights scaled by each measurement's evening gain, and
    #: the gains gathered to scale them, when the level is kept (D-131).
    loudness: npt.NDArray[np.float64]
    evening: npt.NDArray[np.float64]
    #: The crossfade's windows, and the gain ramp's steps.
    fade_in: Samples
    fade_out: Samples
    steps: Samples
    ramp: Samples
    scratch: Samples
    #: The ITD's phase ramp: bin numbers, angles, and the ramp itself.
    bins_: Samples
    angle: Samples
    delay: Spectra
    gather: Spectra
    #: The four filters a pair's loudness is read from, weighted, and the
    #: two ears' cross terms between its sides (D-133).
    weighed: Spectra
    cross: Spectra
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
            rolloff=distance.rolloff,
            min_distance=distance.min_distance,
            ref_distance=distance.ref_distance,
            block=block,
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
            directions=np.zeros((count, 3)),
            vertices=np.zeros((count, 3), dtype=np.int64),
            weights=np.zeros((count, 3)),
            itds=np.zeros(count),
            distance=np.zeros(count),
            target=np.zeros(count),
            reach=np.ones(count),
            loudness=np.zeros((count, 3)),
            evening=np.zeros((count, 3)),
            keep_level=distance.keep_level,
            fade_in=np.linspace(0.0, 1.0, block, dtype=np.float32),
            fade_out=np.linspace(1.0, 0.0, block, dtype=np.float32),
            steps=steps,
            ramp=np.zeros(block, dtype=np.float32),
            scratch=np.zeros(block, dtype=np.float32),
            bins_=np.arange(bins, dtype=np.float32),
            angle=np.zeros(bins, dtype=np.float32),
            delay=np.zeros(bins, dtype=np.complex64),
            gather=np.zeros(bins, dtype=np.complex64),
            weighed=np.zeros((4, bins), dtype=np.complex64),
            cross=np.zeros((2, bins), dtype=np.complex64),
        )
        return space

    # ------------------------------------------------------------ a block

    def render(
        self,
        positions: npt.NDArray[np.float64],
        peaks: npt.NDArray[np.float64],
        bus_l: Samples,
        bus_r: Samples,
    ) -> None:
        """Every source's `src`, placed, summed into the bus."""
        count = self.count
        src = self.src
        sides = self.sides
        for slot in range(count):
            (x, y, z), gain, reach = self._placed(
                positions, self.channels[slot], max(sides[slot], 0)
            )
            self.directions[slot, 0] = x
            self.directions[slot, 1] = y
            self.directions[slot, 2] = z
            self.reach[slot] = reach
            self.target[slot] = gain

        bank = self.bank
        bank.lookup.weigh(self.directions, self.vertices, self.weights, count)
        Lookup.blend(bank.itd, self.vertices, self.weights, self.itds, count)
        if self.keep_level:
            np.take(bank.evening, self.vertices, out=self.evening)
            np.multiply(self.weights, self.evening, out=self.loudness)
        for slot in range(count):
            self._filter(slot)
        if self.pairs:
            self._pair_gains()

        for slot in range(count):
            channel = self.channels[slot]
            row = src[slot]
            gain = float(self.target[slot])
            # The first block after a seek or a swap starts at its gain: it
            # is fresh in its filters too.
            level = gain if self.fresh else float(self.distance[slot])
            if level != gain:
                np.multiply(self.steps, gain - level, out=self.ramp)
                np.add(self.ramp, level, out=self.ramp)
                np.multiply(row, self.ramp, out=row)
            elif gain != 1.0:
                np.multiply(row, gain, out=row)
            self.distance[slot] = gain
            # The meter: what the channel adds, before the HRTF (D-117); a
            # pair's left side is its left meter and its right its right.
            np.abs(row, out=self.scratch)
            loudest = float(self.scratch.max())
            side = sides[slot]
            for which in (0, 1) if side == POINT else (side,):
                if loudest > peaks[channel, which]:
                    peaks[channel, which] = loudest

        if self.fresh or not self.crossfade:
            np.copyto(self.previous_left, self.left)
            np.copyto(self.previous_right, self.right)
            self.fresh = False

        block = self.block
        windowed = self.windowed
        for slot in range(count):
            np.multiply(src[slot], self.fade_out, out=windowed[slot, :block])
            np.multiply(src[slot], self.fade_in, out=windowed[count + slot, :block])
        # numpy's stubs allow only complex128 and float64 for `out`; its float32
        # loops take complex64 and float32, which is the point (D-122).
        np.fft.rfft(windowed, axis=1, norm="ortho", out=self.spectra)  # type: ignore[arg-type]
        fading_out = self.spectra[:count]
        fading_in = self.spectra[count:]
        for ear, (was, now) in enumerate(
            ((self.previous_left, self.left), (self.previous_right, self.right))
        ):
            np.multiply(fading_out, was, out=self.product)
            np.sum(self.product, axis=0, out=self.total[ear])
            np.multiply(fading_in, now, out=self.product)
            np.sum(self.product, axis=0, out=self.half)
            np.add(self.total[ear], self.half, out=self.total[ear])
        np.fft.irfft(self.total, n=bank.nfft, axis=1, norm="ortho", out=self.inverse)  # type: ignore[arg-type]
        np.add(self.tail, self.inverse, out=self.tail)
        self.drain(bus_l, bus_r)
        np.copyto(self.previous_left, self.left)
        np.copyto(self.previous_right, self.right)

    def drain(self, bus_l: Samples, bus_r: Samples) -> None:
        """The accumulator's next block into the bus, and the rest moved up
        a block: what a stopped transport still does, so a pause decays
        rather than cuts, and a resume does not replay it."""
        block = self.block
        tail = self.tail
        np.add(bus_l, tail[0, :block], out=bus_l)
        np.add(bus_r, tail[1, :block], out=bus_r)
        keep = tail.shape[1] - block
        np.copyto(self.shifted[:, :keep], tail[:, block:])
        np.copyto(tail[:, :keep], self.shifted[:, :keep])
        tail[:, keep:].fill(0.0)

    # ------------------------------------------------------------ internal

    def _placed(
        self, positions: npt.NDArray[np.float64], channel: int, side: int
    ) -> tuple[tuple[float, float, float], float, float]:
        """A source's direction, a unit vector; its distance gain; and how
        far out of the centre it is, 0 to 1 (D-130)."""
        x = float(positions[channel, side, 0])
        y = float(positions[channel, side, 1])
        z = float(positions[channel, side, 2])
        r = math.sqrt(x * x + y * y + z * z)
        direction = AHEAD if r == 0.0 else (x / r, y / r, z / r)
        nearest = self.min_distance
        if self.keep_level:
            nearest = max(nearest, self.ref_distance)  # never above 1 (D-131)
        gain = (self.ref_distance / max(r, nearest)) ** self.rolloff
        reach = min(r / self.min_distance, 1.0) if self.min_distance > 0.0 else 1.0
        return direction, gain, reach

    def _filter(self, slot: int) -> None:
        """This block's filter for one channel: three measurements blended per
        ear, and the far ear delayed by the ITD - and in the centre, faded
        towards flat (D-130)."""
        filters = self.bank.filters
        vertices = self.vertices
        weights = self.loudness if self.keep_level else self.weights
        reach = float(self.reach[slot])
        left, right = self.left[slot], self.right[slot]
        for ear, out in ((0, left), (1, right)):
            np.multiply(
                filters[vertices[slot, 0], ear], float(weights[slot, 0]), out=out
            )
            for corner in (1, 2):
                np.multiply(
                    filters[vertices[slot, corner], ear],
                    float(weights[slot, corner]),
                    out=self.gather,
                )
                np.add(out, self.gather, out=out)
            if reach < 1.0:
                np.multiply(out, reach, out=out)
        itd = float(self.itds[slot]) * reach
        # Positive: the left ear is the later, far one (phase 2).
        far = left if itd > 0.0 else right
        if itd != 0.0:
            self._delay(abs(itd))
            np.multiply(far, self.delay, out=far)
        if reach < 1.0:
            # The centre (D-130): the rest of the way to flat, a response of
            # 1 - to both ears for a point, and to its own ear for a pair's
            # side (D-134). Its share of the delay is to the nearest whole
            # sample: a fractional delay of a response reaching up to Nyquist
            # rings through the whole transform and wraps, where the measured
            # responses, which fall away up there, stay compact. The two
            # shares differ by half a sample at most.
            flat = 1.0 - reach
            own = self.sides[slot]
            whole = round(abs(itd))
            for ear, row in ((0, left), (1, right)):
                if own != POINT and own != ear:
                    continue
                if row is far and whole != 0:
                    self._delay(whole)
                    np.multiply(self.delay, flat, out=self.gather)
                    np.add(row, self.gather, out=row)
                else:
                    np.add(row, flat, out=row)

    def _pair_gains(self) -> None:
        """Each pair's share of the gain, into its two sides' targets (D-133):
        `1 / sqrt(loudness)`, the pair's loudness read with its stem's own
        spectra and relative to the stem as mixed, when the level is kept,
        and equal power when it is not."""
        weighed, cross = self.weighed, self.cross
        for index, (first, second) in enumerate(self.pairs):
            if self.keep_level:
                own, other = self.pair_left[index], self.pair_right[index]
                np.multiply(self.left[first], own, out=weighed[0])
                np.multiply(self.right[first], own, out=weighed[1])
                np.multiply(self.left[second], other, out=weighed[2])
                np.multiply(self.right[second], other, out=weighed[3])
                np.conjugate(self.left[second], out=cross[0])
                np.multiply(self.left[first], cross[0], out=cross[0])
                np.conjugate(self.right[second], out=cross[1])
                np.multiply(self.right[first], cross[1], out=cross[1])
                np.add(cross[0], cross[1], out=cross[0])
                loud = (
                    float(np.vdot(weighed[0], weighed[0]).real)
                    + float(np.vdot(weighed[1], weighed[1]).real)
                    + float(np.vdot(weighed[2], weighed[2]).real)
                    + float(np.vdot(weighed[3], weighed[3]).real)
                    + float(np.vdot(self.pair_shared[index], cross[0]).real)
                )
                gain = PAIR_CAP if loud <= 1.0 / PAIR_CAP**2 else 1.0 / math.sqrt(loud)
            else:
                gain = HALF_POWER
            self.target[first] *= gain
            self.target[second] *= gain

    def _delay(self, samples: float) -> None:
        """`self.delay`: a delay of `samples` as a phase ramp over the bins."""
        np.multiply(
            self.bins_, -2.0 * math.pi * samples / self.bank.nfft, out=self.angle
        )
        np.cos(self.angle, out=self.delay.real)
        np.sin(self.angle, out=self.delay.imag)
