"""The engine: the seam 02-architecture.md calls *the* seam.

`process(out)` fills one block of stereo from the snapshot it holds and the
playhead, and moves the playhead on. Offline render at M7 calls it with no
device; the stream calls it through `callback`. Flat at M3: a mono clip to
both ears, a stereo clip as it is, no HRTF.

**Two ways in from the UI thread (D-105).**

- A **snapshot**, for what plays, handed over by `install()` - one
  reference assigned, atomic under the GIL. `process()` takes it up at the
  top of the next block, never in the middle of one, and carries each
  channel's gain across from the snapshot before. The engine never holds
  the only reference to a snapshot: whoever installed it keeps one until
  the engine has moved past it, so nothing is freed here.
- A **command ring**, for how loud each channel is and for seeking: a
  fixed array of four-number commands, written by the UI thread and read
  by this one, each side moving only its own counter. A gain names the
  snapshot generation it was worked out against, and one naming another is
  dropped - after a reorder, its channel's index means someone else.

**A gain change ramps across one block** (05, *Parameter smoothing*): each
channel's gain moves from where the last block left it to its target in
equal steps, the last sample landing on the target. A mute is a gain of
nothing, so it ramps too, and does not click.

**Nothing on the audio thread allocates an array** (D-106). The bus and a
channel's rows are made once, one contiguous row per ear, and every
operation writes into them with `out=` - never broadcasting, which makes
numpy allocate behind `out=`. No lock, no logging, no string is built.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import numpy.typing as npt

from immersive.audio.device import DEFAULT_BLOCK
from immersive.audio.dsp import ramp_steps
from immersive.audio.scheduler import Snapshot, empty, fill

#: How many commands can wait between two blocks. A gain is sent once per
#: gesture, so this many only pile up while nothing is playing.
RING: Final = 4096

#: What a command is, as the ring's first number.
GAIN: Final = 0.0
SEEK: Final = 1.0


class Engine:
    """One block of stereo at a time, from a snapshot and a playhead."""

    def __init__(self, block: int = DEFAULT_BLOCK) -> None:
        self.block = block
        self._current = empty()
        self._next = self._current
        self._playhead = 0
        #: kind, generation, channel, value - one command a row.
        self._ring = np.zeros((RING, 4), dtype=np.float64)
        self._written = 0  # the UI thread's counter
        self._read = 0  # the audio thread's counter
        self._bus = np.zeros((2, block), dtype=np.float32)
        self._bus_l, self._bus_r = self._bus[0], self._bus[1]
        self._lane = np.zeros((2, block), dtype=np.float32)
        self._lane_l, self._lane_r = self._lane[0], self._lane[1]
        self._steps = ramp_steps(block)
        self._ramp = np.zeros(block, dtype=np.float32)
        self._scratch = np.zeros(block, dtype=np.float32)
        #: The bus's highest level on each side since the peaks were taken.
        self._peaks = np.zeros(2, dtype=np.float64)
        self._xruns = np.zeros(1, dtype=np.int64)

    # ------------------------------------------------------ the UI thread

    def install(self, snapshot: Snapshot) -> None:
        """Play `snapshot` from the next block. Keep a reference to it until
        `holds()` says the engine has let it go."""
        self._next = snapshot

    def holds(self, snapshot: Snapshot) -> bool:
        """Whether the engine may still read `snapshot`: the one playing, or
        the one waiting to be taken up."""
        return snapshot is self._current or snapshot is self._next

    def send_gain(self, generation: int, channel: int, gain: float) -> bool:
        """Ramp channel `channel` of snapshot `generation` to `gain`, a
        factor. False when the ring is full."""
        return self._send(GAIN, generation, channel, gain)

    def seek(self, sample: int) -> bool:
        """Play the next block from `sample`. False when the ring is full."""
        return self._send(SEEK, 0, 0, sample)

    @property
    def playhead(self) -> int:
        """Where the next block starts."""
        return self._playhead

    @property
    def xruns(self) -> int:
        """Blocks the stream could not be given in time, or not whole."""
        return int(self._xruns[0])

    def take_peaks(self) -> tuple[float, float]:
        """The bus's highest level on each side since the last time, and
        start again. A block that lands between the two is one block of a
        meter, which nobody sees (05, *Metering*)."""
        left, right = float(self._peaks[0]), float(self._peaks[1])
        self._peaks.fill(0)
        return left, right

    def _send(self, kind: float, generation: int, channel: int, value: float) -> bool:
        if self._written - self._read >= RING:
            return False
        slot = self._ring[self._written % RING]
        slot[0], slot[1], slot[2], slot[3] = kind, generation, channel, value
        # Published last: the audio thread reads nothing past this count.
        self._written += 1
        return True

    # --------------------------------------------------- the audio thread

    def callback(self, outdata: Any, frames: int, time: Any, status: Any) -> None:
        """What the stream calls. An underflow is counted; a block of a size
        the stream did not promise is silence, and counted too."""
        if status is not None and status.output_underflow:
            np.add(self._xruns, 1, out=self._xruns)
        if frames != self.block:
            outdata.fill(0)
            np.add(self._xruns, 1, out=self._xruns)
            return
        self.process(outdata)

    def process(self, out: npt.NDArray[np.float32]) -> None:
        """Fill `out`, `(block, 2)`, with the next block. No array is made
        below this line."""
        snapshot = self._next
        if snapshot is not self._current:
            self._take_up(snapshot)
        self._drain(snapshot)

        t = self._playhead
        bus_l, bus_r = self._bus_l, self._bus_r
        lane_l, lane_r = self._lane_l, self._lane_r
        bus_l.fill(0)
        bus_r.fill(0)
        targets, levels = snapshot.targets, snapshot.levels
        lanes = snapshot.lanes
        for index in range(len(lanes)):
            target = float(targets[index])
            level = float(levels[index])
            if target == 0.0 and level == 0.0:
                continue
            if not fill(lanes[index], t, lane_l, lane_r):
                levels[index] = target
                continue
            if level != target:
                ramp = self._ramp
                np.multiply(self._steps, target - level, out=ramp)
                np.add(ramp, level, out=ramp)
                np.multiply(lane_l, ramp, out=lane_l)
                np.multiply(lane_r, ramp, out=lane_r)
                levels[index] = target
            elif target != 1.0:
                np.multiply(lane_l, target, out=lane_l)
                np.multiply(lane_r, target, out=lane_r)
            np.add(bus_l, lane_l, out=bus_l)
            np.add(bus_r, lane_r, out=bus_r)

        self._peak(bus_l, 0)
        self._peak(bus_r, 1)
        np.copyto(out[:, 0], bus_l)
        np.copyto(out[:, 1], bus_r)
        self._playhead = t + self.block

    def _take_up(self, snapshot: Snapshot) -> None:
        """Start playing `snapshot`, each channel ramping from the gain it
        had in the one before - if the one before is the one it was built
        against. Two installed within one block skip a snapshot, and its
        channels' places mean nothing to this one, so it starts at its
        targets. The one before is not freed here: whoever installed it
        still holds it."""
        if self._current.generation == snapshot.based_on:
            before = self._current.levels
            levels = snapshot.levels
            for index, was in enumerate(snapshot.carry):
                if was >= 0:
                    levels[index] = before[was]
            # Let go before the swap: once `_current` moves on, the UI thread
            # may drop the old snapshot, and a local still holding its array
            # would free it here, when this returns.
            del before
        self._current = snapshot

    def _drain(self, snapshot: Snapshot) -> None:
        """Apply every command sent since the last block, oldest first."""
        written = self._written
        ring = self._ring
        targets = snapshot.targets
        while self._read < written:
            command = ring[self._read % RING]
            if command[0] == SEEK:
                self._playhead = int(command[3])
            elif command[1] == snapshot.generation and 0 <= command[2] < len(targets):
                targets[int(command[2])] = command[3]
            self._read += 1

    def _peak(self, side: npt.NDArray[np.float32], which: int) -> None:
        np.abs(side, out=self._scratch)
        loudest = self._scratch.max()
        if loudest > self._peaks[which]:
            self._peaks[which] = loudest
