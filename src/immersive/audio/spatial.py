"""The spatial path: each non-bypassed channel heard from where it is (05,
*Per-block processing*).

A `Space` is built on the UI thread for one snapshot. It holds the bank,
the distance settings and every buffer a block writes, sized to the
snapshot's spatial channels and the bank's `nfft`, so `render` makes no
array (D-106). Per block, for each spatial channel:

1. its **mono point** (D-16) has already been written into `src` by the
   engine, after the channel's gain;
2. **distance** (D-21): `(ref / max(r, min)) ** rolloff`, ramped across the
   block from the last block's value. The channel's meter is read here,
   before the HRTF (D-117);
3. **its filter**: the direction weighed by the lookup, the three nearest
   measurements' spectra blended per ear, and the far ear delayed by the
   blended ITD as a phase ramp, so both delays are non-negative (05);
4. **the crossfade** (D-37): the source windowed twice - fading out against
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
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from immersive.audio.dsp import ramp_steps
from immersive.audio.hrtf.bank import Bank
from immersive.audio.hrtf.lookup import Lookup
from immersive.core.model import Distance

#: Where a source at the listener's own position is heard from.
AHEAD: Final = (0.0, 1.0, 0.0)

Samples = npt.NDArray[np.float32]
Spectra = npt.NDArray[np.complex64]


@dataclass(eq=False)
class Space:
    """One snapshot's spatial channels, and everything a block writes."""

    bank: Bank
    #: Each spatial channel's index among the snapshot's lanes.
    channels: tuple[int, ...]
    rolloff: float
    min_distance: float
    ref_distance: float
    block: int
    #: `[S, block]` each channel's mono point, written by the engine.
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
    #: Each channel's distance gain as the last block ended.
    distance: npt.NDArray[np.float64]
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
    ) -> Space:
        """On the UI thread: every buffer, sized once."""
        count = len(channels)
        block, nfft = bank.block, bank.nfft
        bins = nfft // 2 + 1
        steps = ramp_steps(block)
        space = cls(
            bank=bank,
            channels=channels,
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
            fade_in=np.linspace(0.0, 1.0, block, dtype=np.float32),
            fade_out=np.linspace(1.0, 0.0, block, dtype=np.float32),
            steps=steps,
            ramp=np.zeros(block, dtype=np.float32),
            scratch=np.zeros(block, dtype=np.float32),
            bins_=np.arange(bins, dtype=np.float32),
            angle=np.zeros(bins, dtype=np.float32),
            delay=np.zeros(bins, dtype=np.complex64),
            gather=np.zeros(bins, dtype=np.complex64),
        )
        for slot, channel in enumerate(channels):
            _, gain = space._placed(positions, channel)
            space.distance[slot] = gain
        return space

    # ------------------------------------------------------------ a block

    def render(
        self,
        positions: npt.NDArray[np.float64],
        peaks: npt.NDArray[np.float64],
        bus_l: Samples,
        bus_r: Samples,
    ) -> None:
        """Every spatial channel's `src`, placed, summed into the bus."""
        count = self.count
        src = self.src
        for slot in range(count):
            channel = self.channels[slot]
            (x, y, z), gain = self._placed(positions, channel)
            self.directions[slot, 0] = x
            self.directions[slot, 1] = y
            self.directions[slot, 2] = z
            row = src[slot]
            level = float(self.distance[slot])
            if level != gain:
                np.multiply(self.steps, gain - level, out=self.ramp)
                np.add(self.ramp, level, out=self.ramp)
                np.multiply(row, self.ramp, out=row)
                self.distance[slot] = gain
            elif gain != 1.0:
                np.multiply(row, gain, out=row)
            # The meter: what the channel adds, before the HRTF (D-117).
            np.abs(row, out=self.scratch)
            loudest = float(self.scratch.max())
            if loudest > peaks[channel, 0]:
                peaks[channel, 0] = loudest
                peaks[channel, 1] = loudest

        bank = self.bank
        bank.lookup.weigh(self.directions, self.vertices, self.weights, count)
        Lookup.blend(bank.itd, self.vertices, self.weights, self.itds, count)
        for slot in range(count):
            self._filter(slot)
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
        self, positions: npt.NDArray[np.float64], channel: int
    ) -> tuple[tuple[float, float, float], float]:
        """A channel's direction, a unit vector, and its distance gain."""
        x = float(positions[channel, 0])
        y = float(positions[channel, 1])
        z = float(positions[channel, 2])
        r = math.sqrt(x * x + y * y + z * z)
        direction = AHEAD if r == 0.0 else (x / r, y / r, z / r)
        gain = (self.ref_distance / max(r, self.min_distance)) ** self.rolloff
        return direction, gain

    def _filter(self, slot: int) -> None:
        """This block's filter for one channel: three measurements blended per
        ear, and the far ear delayed by the ITD."""
        filters = self.bank.filters
        vertices = self.vertices
        weights = self.weights
        for ear, out in ((0, self.left[slot]), (1, self.right[slot])):
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
        itd = float(self.itds[slot])
        if itd != 0.0:
            # Positive: the left ear is the later, far one (phase 2).
            far = self.left[slot] if itd > 0.0 else self.right[slot]
            np.multiply(
                self.bins_, -2.0 * math.pi * abs(itd) / self.bank.nfft, out=self.angle
            )
            np.cos(self.angle, out=self.delay.real)
            np.sin(self.angle, out=self.delay.imag)
            np.multiply(far, self.delay, out=far)
