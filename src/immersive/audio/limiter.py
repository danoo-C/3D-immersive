"""The master limiter (05, *The limiter*): one fixed design (D-54), computed
a block at a time with no array made (D-106, D-123).

**Brickwall, and why it is.** Every sample needs some reduction, in dB, to
come out under the ceiling: none below the knee, all of its excess above
it, and a soft curve between. That need is held forward over the lookahead,
released slowly, and averaged over the lookahead, and the average is the
reduction applied to the audio 72 samples later. At a peak's own sample the
average is of 72 values, each at least that peak's need, so it is at least
the need: no sample passes the ceiling. The average also makes the attack a
ramp that begins 72 samples before the peak.

**No loop per sample.** The release, `r = max(h, a·r_before)`, is a
recursion, but scaled by `a^-n` it is a running maximum, which numpy has,
and the average is a difference of running sums. So a block is some thirty
numpy calls over rows made once, whatever its size.

**Always delayed, limited while on** (D-124). The delay is what the lookahead
costs, and it stays when the limiter is off so a switch moves nothing in
time. The switch fades across a block from one to the other (D-126), so the
reduction is always computed, on or off, and always current.

Some numpy calls allocate behind `out=`, measured while planning: `np.clip`
with Python bounds, `np.cumsum`, and any ufunc reading float32 into
float64. None of them is used here.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np
import numpy.typing as npt

from immersive.audio.dsp import ramp_steps
from immersive.core.time import SAMPLE_RATE

#: 1.5 ms: how far ahead it looks, and so how late everything it passes is.
LOOKAHEAD: Final = round(0.0015 * SAMPLE_RATE)
CEILING_DB: Final = -0.3
KNEE_DB: Final = 2.0
#: The release's time constant, seconds.
RELEASE: Final = 0.050
#: How far below the ceiling it aims: float32 rounding would otherwise put
#: a sample one step past -0.3 dBFS. 10⁻⁵ dB is a factor of 1.0000012.
MARGIN_DB: Final = 1e-5
#: Below this a release has ended: it is set to nothing rather than decaying
#: into subnormal numbers, which are slow.
SETTLED_DB: Final = 1e-12

Samples = npt.NDArray[np.float32]
Row = npt.NDArray[np.float64]


def reduction(level_db: float) -> float:
    """The static curve: how many dB a sample at `level_db` is turned down
    (Giannoulis, Massberg and Reiss's soft knee at an infinite ratio). The
    knee is centred on the ceiling, 2 dB wide, and what comes out of its top
    is the ceiling: so reduction starts 1 dB under the ceiling, and above
    the knee all of the excess over the ceiling is taken off."""
    ceiling = CEILING_DB - MARGIN_DB
    into = min(max(level_db - (ceiling - KNEE_DB / 2), 0.0), KNEE_DB)
    return into * into / (2 * KNEE_DB) + max(level_db - (ceiling + KNEE_DB / 2), 0.0)


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
