"""The engine's block as Python, as it was before it was compiled (M4 phase
12, D-138): the reference the kernels are held to.

Each function is the package's as it stood at phase 11, with a lane's clip
ends worked out from its clips, which the compiled lane no longer keeps.
Nothing in the package imports this; the kernels are what play.
"""

from __future__ import annotations

import bisect
import math

import numpy as np

from immersive.audio.dsp import Samples, ramp_steps
from immersive.audio.limiter import (
    CEILING_DB,
    KNEE_DB,
    LOOKAHEAD,
    MARGIN_DB,
    RELEASE,
    SETTLED_DB,
)
from immersive.audio.scheduler import MONO, STEREO, Lane, Placed
from immersive.core.time import SAMPLE_RATE


def fill(lane: Lane, t: int, left: Samples, right: Samples, mono: Samples) -> int:
    """Write `lane`'s share of the block starting at sample `t`: a stereo
    clip's sides into `left` and `right`, a mono clip into `mono`, silence
    where no clip of that kind plays. Which rows were written, as `STEREO`
    and `MONO` bits, so a silent channel can be passed over and a row no
    clip wrote is not read. A clip whose sample is not here plays silence,
    and the rest of the lane plays."""
    size = left.shape[0]
    stop = t + size
    clips = lane.clips
    index = bisect.bisect_right([clip.end for clip in clips], t)
    wrote = 0
    while index < len(clips):
        clip = clips[index]
        if clip.start >= stop:
            break
        index += 1
        sample = clip.audio
        if sample is None:
            continue
        first = max(t, clip.start)
        last = min(stop, clip.end)
        read = clip.offset + (first - clip.start)
        count = last - first
        at = first - t
        if sample.shape[1] == 1:
            if not wrote & MONO:
                mono.fill(0)
                wrote |= MONO
            _place(clip, mono[at : at + count], sample[read : read + count, 0], first)
        else:
            if not wrote & STEREO:
                left.fill(0)
                right.fill(0)
                wrote |= STEREO
            _place(clip, left[at : at + count], sample[read : read + count, 0], first)
            _place(
                clip,
                right[at : at + count],
                sample[read : read + count, sample.shape[1] - 1],
                first,
            )
    return wrote


def _place(clip: Placed, into: Samples, samples: Samples, first: int) -> None:
    """One side of `clip` from timeline sample `first`: its samples, at its
    gain, through its fades."""
    np.copyto(into, samples)
    if clip.gain != 1.0:
        np.multiply(into, clip.gain, out=into)
    count = into.shape[0]
    if clip.head is not None:
        _envelope(into, clip.head, first - clip.start, count)
    if clip.tail is not None:
        length = clip.tail.shape[0]
        _envelope(into, clip.tail, first - (clip.end - length), count)


def _envelope(row: Samples, table: Samples, into: int, count: int) -> None:
    """Multiply the part of `row` that lies over `table` by it.

    `into` is how far into the table the row's first sample is - negative
    when the row begins before it - and `count` how long the row is.
    """
    begin = max(into, 0)
    end = min(into + count, table.shape[0])
    if begin >= end:
        return
    part = row[begin - into : end - into]
    np.multiply(part, table[begin:end], out=part)


class Limiter:
    """D-54's limiter for blocks of `block` frames, in place."""

    def __init__(self, block: int) -> None:
        ahead = LOOKAHEAD
        self.block = block
        self._decay = math.exp(-1.0 / (RELEASE * SAMPLE_RATE))
        steps = np.arange(block, dtype=np.float64)
        #: `a^-n` to scale the release into a running maximum, `a^n` back.
        self._up = self._decay**-steps
        self._down = self._decay**steps
        #: The release as the last block left it.
        self._released = 0.0
        #: Each row keeps the lookahead's worth of the block before at its
        #: head, then this block's.
        self._delay = np.zeros((2, ahead + block), dtype=np.float32)
        self._need = np.zeros(ahead + block, dtype=np.float64)
        self._release = np.zeros(ahead + block, dtype=np.float64)
        #: The running sums the average is a difference of, from a 0.
        self._sums = np.zeros(ahead + block + 1, dtype=np.float64)
        #: The sliding maximum's two rows, written in turn.
        self._wider = np.zeros(ahead + block, dtype=np.float64)
        self._widest = np.zeros(ahead + block, dtype=np.float64)
        self._held = np.zeros(block, dtype=np.float64)
        self._scaled = np.zeros(block, dtype=np.float64)
        self._level = np.zeros(block, dtype=np.float64)
        self._knee = np.zeros(block, dtype=np.float64)
        self._peak = np.zeros(block, dtype=np.float32)
        self._other = np.zeros(block, dtype=np.float32)
        self._gain = np.zeros(block, dtype=np.float32)
        self._steps = ramp_steps(block)
        self._ramp = np.zeros(block, dtype=np.float32)
        # The hold, a maximum over `ahead + 1` samples, by doubling: windows
        # of 2, 4, 8 ... up to the largest that fits, then two of those
        # overlapping to cover the rest.
        self._doublings: list[int] = []
        span = 1
        while span * 2 <= ahead + 1:
            self._doublings.append(span)
            span *= 2
        self._overlap = ahead + 1 - span

    def process(self, left: Samples, right: Samples, was: float, now: float) -> None:
        """`left` and `right` delayed by `LOOKAHEAD`, and limited as far as
        the switch says: `was` at the block's start, `now` at its end, each
        1 for on and 0 for off."""
        self._measure(left, right)
        self._hold()
        self._release_and_average()
        self._apply(left, right, was, now)

    # ------------------------------------------------------------ internal

    def _measure(self, left: Samples, right: Samples) -> None:
        """Into the delay, and each sample's need into the reductions ahead:
        the louder side's, so a peak on one side turns both down alike."""
        ahead = LOOKAHEAD
        np.copyto(self._delay[0, ahead:], left)
        np.copyto(self._delay[1, ahead:], right)
        peak, level, knee = self._peak, self._level, self._knee
        np.abs(left, out=peak)
        np.abs(right, out=self._other)
        np.maximum(peak, self._other, out=peak)
        np.copyto(level, peak)  # to float64 here, not inside a ufunc
        np.maximum(level, 1e-12, out=level)
        np.log10(level, out=level)
        np.multiply(level, 20.0, out=level)
        # `reduction()`, a block at a time.
        ceiling = CEILING_DB - MARGIN_DB
        np.subtract(level, ceiling - KNEE_DB / 2, out=knee)
        np.maximum(knee, 0.0, out=knee)
        np.minimum(knee, KNEE_DB, out=knee)
        np.multiply(knee, knee, out=knee)
        np.multiply(knee, 1.0 / (2 * KNEE_DB), out=knee)
        np.subtract(level, ceiling + KNEE_DB / 2, out=level)
        np.maximum(level, 0.0, out=level)
        np.add(knee, level, out=self._need[ahead:])

    def _hold(self) -> None:
        """Each sample's need, held forward: the most any of the next
        `LOOKAHEAD` samples, and its own, needs."""
        size = self._need.shape[0]
        source, into, spare = self._need, self._wider, self._widest
        for span in self._doublings:
            np.maximum(
                source[: size - span], source[span:size], out=into[: size - span]
            )
            size -= span
            source, into, spare = into, spare, into
        block, overlap = self.block, self._overlap
        np.maximum(source[:block], source[overlap : overlap + block], out=self._held)

    def _release_and_average(self) -> None:
        """The held need, released with a 50 ms time constant and carried
        across blocks, then averaged over `LOOKAHEAD` samples: the reduction
        each sample of the delayed block gets, in dB, into `_scaled`."""
        ahead, block = LOOKAHEAD, self.block
        released = self._release[ahead:]
        np.multiply(self._held, self._up, out=released)
        carried = self._decay * self._released
        if carried > released[0]:
            released[0] = carried
        np.maximum.accumulate(released, out=self._scaled)
        np.multiply(self._scaled, self._down, out=released)
        last = float(released[block - 1])
        self._released = last if last > SETTLED_DB else 0.0
        sums = self._sums
        np.add.accumulate(self._release, out=sums[1:])
        np.subtract(
            sums[ahead + 1 : ahead + 1 + block], sums[1 : 1 + block], out=self._scaled
        )
        np.multiply(self._scaled, 1.0 / ahead, out=self._scaled)

    def _apply(self, left: Samples, right: Samples, was: float, now: float) -> None:
        """The delayed block out, at the reduction as far as the switch is on;
        then every row moved on by a block."""
        ahead, block = LOOKAHEAD, self.block
        delay, gain = self._delay, self._gain
        if was == 0.0 and now == 0.0:
            np.copyto(left, delay[0, :block])
            np.copyto(right, delay[1, :block])
        else:
            scaled = self._scaled
            np.multiply(scaled, -1.0 / 20.0, out=scaled)
            np.power(10.0, scaled, out=scaled)
            np.copyto(gain, scaled, casting="same_kind")
            if was != 1.0 or now != 1.0:
                # Switching: from no reduction to all of it, or back, as a
                # fade across the block - `1 - k·(1 - gain)`.
                ramp = self._ramp
                np.multiply(self._steps, now - was, out=ramp)
                np.add(ramp, was, out=ramp)
                np.subtract(gain, 1.0, out=gain)
                np.multiply(gain, ramp, out=gain)
                np.add(gain, 1.0, out=gain)
            np.multiply(delay[0, :block], gain, out=left)
            np.multiply(delay[1, :block], gain, out=right)
        # A device's block is never shorter than the lookahead - 256 frames
        # at least, against 72 - so these copies do not overlap themselves.
        # A test's shorter block still comes out right: numpy then copies
        # through a buffer of its own.
        np.copyto(delay[:, :ahead], delay[:, block:])
        np.copyto(self._need[:ahead], self._need[block:])
        np.copyto(self._release[:ahead], self._release[block:])
