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

**Compiled** (D-138). The block is `_limit`, one kernel without the GIL,
the numpy it replaced rewritten as loops over the same float64 arithmetic
and held to it by the tests (`tests/reference_engine.py`). It keeps that
numpy's shape: the release, `r = max(h, a·r_before)`, is a recursion, but
scaled by `a^-n` it is a running maximum, and the average is a difference
of running sums.

**Always delayed, limited while on** (D-124). The delay is what the lookahead
costs, and it stays when the limiter is off so a switch moves nothing in
time. The switch fades across a block from one to the other (D-126), so the
reduction is always computed, on or off, and always current.

It makes no array: a kernel cannot (D-138).
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np
import numpy.typing as npt

from immersive.audio.compiled import kernel
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

#: What `_limit` takes besides a block and its switch, in its order.
Arguments = tuple[
    Samples,
    Row,
    Row,
    Row,
    Row,
    Row,
    Row,
    Row,
    Samples,
    Samples,
    Row,
    Row,
    npt.NDArray[np.int64],
    int,
    float,
    Row,
]


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
        #: The release as the last block left it, where the kernel keeps it.
        self._state = np.zeros(1)
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
        self._gain = np.zeros(block, dtype=np.float32)
        self._steps = ramp_steps(block)
        # The hold, a maximum over `ahead + 1` samples, by doubling: windows
        # of 2, 4, 8 ... up to the largest that fits, then two of those
        # overlapping to cover the rest.
        doublings = []
        span = 1
        while span * 2 <= ahead + 1:
            doublings.append(span)
            span *= 2
        self._doublings = np.array(doublings, dtype=np.int64)
        self._overlap = ahead + 1 - span

    @property
    def arguments(self) -> Arguments:
        """What `_limit` takes besides a block and its switch: the engine's
        block kernel hands these on (phase 12)."""
        return (
            self._delay,
            self._need,
            self._release,
            self._sums,
            self._wider,
            self._widest,
            self._held,
            self._scaled,
            self._gain,
            self._steps,
            self._up,
            self._down,
            self._doublings,
            self._overlap,
            self._decay,
            self._state,
        )

    def process(self, left: Samples, right: Samples, was: float, now: float) -> None:
        """`left` and `right` delayed by `LOOKAHEAD`, and limited as far as
        the switch says: `was` at the block's start, `now` at its end, each
        1 for on and 0 for off."""
        _limit(left, right, float(was), float(now), *self.arguments)


@kernel
def _limit(
    left: Samples,
    right: Samples,
    was: float,
    now: float,
    delay: Samples,
    need: Row,
    release: Row,
    sums: Row,
    wider: Row,
    widest: Row,
    held: Row,
    scaled: Row,
    gain: Samples,
    steps: Samples,
    up: Row,
    down: Row,
    doublings: npt.NDArray[np.int64],
    overlap: int,
    decay: float,
    state: Row,
) -> None:
    """A block, limited: measured, held, released and averaged, applied."""
    ahead = LOOKAHEAD
    block = left.shape[0]

    # Into the delay, and each sample's need into the reductions ahead: the
    # louder side's, so a peak on one side turns both down alike.
    ceiling = CEILING_DB - MARGIN_DB
    for i in range(block):
        delay[0, ahead + i] = left[i]
        delay[1, ahead + i] = right[i]
        level = float(max(abs(left[i]), abs(right[i])))
        level = max(level, 1e-12)
        level = math.log10(level) * 20.0
        knee = level - (ceiling - KNEE_DB / 2)
        knee = min(max(knee, 0.0), KNEE_DB)
        knee = knee * knee * (1.0 / (2 * KNEE_DB))
        need[ahead + i] = knee + max(level - (ceiling + KNEE_DB / 2), 0.0)

    # Held forward: the most any of the next `LOOKAHEAD` samples, and its
    # own, needs.
    size = need.shape[0]
    source, into, spare = need, wider, widest
    for span in doublings:
        for i in range(size - span):
            into[i] = max(source[i], source[i + span])
        size -= span
        source, into, spare = into, spare, into
    for i in range(block):
        held[i] = max(source[i], source[overlap + i])

    # Released with a 50 ms time constant and carried across blocks, then
    # averaged over `LOOKAHEAD` samples: each sample's reduction, in dB.
    for i in range(block):
        release[ahead + i] = held[i] * up[i]
    carried = decay * state[0]
    if carried > release[ahead]:
        release[ahead] = carried
    running = release[ahead]
    for i in range(block):
        running = max(running, release[ahead + i])
        scaled[i] = running
    for i in range(block):
        release[ahead + i] = scaled[i] * down[i]
    last = release[ahead + block - 1]
    state[0] = last if last > SETTLED_DB else 0.0
    total = 0.0
    for i in range(ahead + block):
        total += release[i]
        sums[i + 1] = total
    for i in range(block):
        scaled[i] = (sums[ahead + 1 + i] - sums[1 + i]) * (1.0 / ahead)

    # The delayed block out, at the reduction as far as the switch is on;
    # then every row moved on by a block.
    if was == 0.0 and now == 0.0:
        for i in range(block):
            left[i] = delay[0, i]
            right[i] = delay[1, i]
    else:
        for i in range(block):
            gain[i] = np.float32(10.0 ** (scaled[i] * (-1.0 / 20.0)))
        if was != 1.0 or now != 1.0:
            # Switching: from no reduction to all of it, or back, as a fade
            # across the block - `1 - k·(1 - gain)`.
            rise = np.float32(now - was)
            start = np.float32(was)
            one = np.float32(1.0)
            for i in range(block):
                gain[i] = (gain[i] - one) * (steps[i] * rise + start) + one
        for i in range(block):
            left[i] = delay[0, i] * gain[i]
            right[i] = delay[1, i] * gain[i]
    for i in range(ahead):
        delay[0, i] = delay[0, block + i]
        delay[1, i] = delay[1, block + i]
        need[i] = need[block + i]
        release[i] = release[block + i]
