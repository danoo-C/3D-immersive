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
  fixed array of seven-number commands, written by the UI thread and read
  by this one, each side moving only its own counter. A gain names the
  snapshot generation it was worked out against, and one naming another is
  dropped - after a reorder, its channel's index means someone else.

**A gain change ramps across one block** (05, *Parameter smoothing*): each
channel's gain moves from where the last block left it to its target in
equal steps, the last sample landing on the target. A mute is a gain of
nothing, so it ramps too, and does not click. A channel's gain is four
factors (D-125), a mono clip's to each ear and a stereo clip's two sides,
which is how a bypassed channel's pan reaches it, and each ramps.

**The master gain ramps the whole bus** after every channel and the
audition have joined it, from the snapshot's `master` as `MASTER` commands
change it (D-126). **The limiter** follows it (D-54, D-123), and the master
meter reads what the limiter lets out. Everything leaves the engine
`latency` frames after the block it was read in, whether the limiter is on
or off (D-124): a render drops that many frames at its start.

**The transport lives here too** (phase 9). Playing, the loop region and
its switch arrive through the ring, ordered with seeks. Stopped, a block
plays no clip and leaves the playhead where it is, but the ring is still
drained and an audition still plays. A block that crosses the loop's end
is rendered in pieces, the playhead wrapping to the loop's start between
them, so the join has no gap and no repeated sample. A playhead already
past the loop's end plays on.

**An audition is a voice** (D-107): one decoded sample, summed into the bus
after the channels - so no channel's gain, mute or solo reaches it - from
its first frame to its last. It is handed over as a snapshot is, and taken
up at the top of a block, so the engine never holds the only reference to
one, and never frees its array. A voice stopped or replaced while it still
sounds plays one block more, falling to silence, so it does not click
(D-115).

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
from immersive.audio.limiter import LOOKAHEAD, Limiter
from immersive.audio.scheduler import MONO, STEREO, Lane, Sides, Snapshot, empty, fill
from immersive.core.model import MIN_LOOP_LENGTH

#: How many commands can wait between two blocks. A gain is sent once per
#: gesture, so this many only pile up before the stream has first opened.
RING: Final = 4096

#: What a command is, as the ring's first number. The other six are, for
#: a gain, its snapshot's generation, the channel and its four factors
#: (D-125); for a seek, the sample, third; for playing, 1 or 0, third; for
#: the loop, its start, its end, and 1 or 0 for whether it is on; for
#: repeating, the project's end, first, and 1 or 0, third; for a position,
#: its snapshot's generation, the channel, and x, y and z (D-121); for the
#: master, its snapshot's generation, the gain, and 1 or 0 for the limiter
#: (D-126).
GAIN: Final = 0.0
SEEK: Final = 1.0
PLAY: Final = 2.0
LOOP: Final = 3.0
REPEAT: Final = 4.0
POSITION: Final = 5.0
MASTER: Final = 6.0

#: Numbers a command carries, its kind first. Seven since M4, for a
#: channel's four factors.
WIDTH: Final = 7

#: The shortest loop the engine will wrap (D-108): so a block is at most
#: `block // SHORTEST_LOOP + 2` pieces. The model refuses a shorter region.
SHORTEST_LOOP: Final = MIN_LOOP_LENGTH


class Voice:
    """One sample, auditioned: the decoded array and how far through it the
    engine is. The position is written only by the audio thread."""

    def __init__(self, audio: npt.NDArray[np.float32]) -> None:
        self.audio = audio
        self.frames = int(audio.shape[0])
        self.last = int(audio.shape[1]) - 1
        self.position = 0

    @property
    def finished(self) -> bool:
        return self.position >= self.frames


class Engine:
    """One block of stereo at a time, from a snapshot and a playhead."""

    def __init__(self, block: int = DEFAULT_BLOCK) -> None:
        self.block = block
        self._current = empty()
        self._next = self._current
        self._voice: Voice | None = None
        self._next_voice: Voice | None = None
        #: A voice stopped or replaced mid-sample, for its one falling block.
        self._fading: Voice | None = None
        self._playhead = 0
        self._playing = False
        self._loop_start = 0
        self._loop_end = 0
        self._looping = False
        self._repeat_end = 0
        self._repeating = False
        #: kind, then three numbers that mean what the kind says.
        self._ring = np.zeros((RING, WIDTH), dtype=np.float64)
        self._written = 0  # the UI thread's counter
        self._read = 0  # the audio thread's counter
        self._bus = np.zeros((2, block), dtype=np.float32)
        self._bus_l, self._bus_r = self._bus[0], self._bus[1]
        self._lane = np.zeros((3, block), dtype=np.float32)
        self._lane_l, self._lane_r, self._lane_m = self._lane
        self._steps = ramp_steps(block)
        #: A block's fall to silence: its last sample is at 0.
        self._fall = np.subtract(np.float32(1.0), self._steps)
        self._ramp = np.zeros(block, dtype=np.float32)
        self._scratch = np.zeros(block, dtype=np.float32)
        #: Where a block's pieces start on the timeline, where in the block,
        #: and how long: more than one only where a loop wraps.
        self._pieces = np.zeros((block // SHORTEST_LOOP + 2, 3), dtype=np.int64)
        #: The master gain and the limiter's switch as the last block left
        #: them (D-126).
        self._master_level = 1.0
        self._switch = 1.0
        self._limiter = Limiter(block)
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

    def audition(self, voice: Voice | None) -> None:
        """Play `voice` from its first frame, from the next block, in place
        of any other; `None` for silence. Keep a reference until
        `holds_voice()` says the engine has let it go."""
        self._next_voice = voice

    def holds_voice(self, voice: Voice) -> bool:
        return (
            voice is self._voice or voice is self._next_voice or voice is self._fading
        )

    @property
    def auditioning(self) -> bool:
        """Whether a voice is sounding, or about to: the UI thread's view."""
        voice = self._next_voice
        return voice is not None and not voice.finished

    def send_gain(self, generation: int, channel: int, sides: Sides) -> bool:
        """Ramp channel `channel` of snapshot `generation` to its four
        factors (D-125). False when the ring is full."""
        return self._send(GAIN, generation, channel, *sides)

    def send_master(self, generation: int, gain: float, limiter: bool) -> bool:
        """Ramp the master to `gain`, a factor, and switch the limiter, as of
        snapshot `generation` (D-126). False when the ring is full."""
        return self._send(MASTER, generation, gain, 1.0 if limiter else 0.0)

    def send_position(
        self, generation: int, channel: int, x: float, y: float, z: float
    ) -> bool:
        """Place channel `channel` of snapshot `generation` at `(x, y, z)`,
        metres, from the next block (D-121). False when the ring is full."""
        return self._send(POSITION, generation, channel, x, y, z)

    def seek(self, sample: int) -> bool:
        """Play the next block from `sample`. False when the ring is full."""
        return self._send(SEEK, 0, 0, sample)

    def set_playing(self, playing: bool) -> bool:
        """Play from the playhead, or stop where it is. False when full."""
        return self._send(PLAY, 0, 0, 1.0 if playing else 0.0)

    def set_loop(self, start: int, end: int, on: bool) -> bool:
        """Loop `[start, end)` while `on`. A region shorter than
        `SHORTEST_LOOP` never loops. False when the ring is full."""
        return self._send(LOOP, start, end, 1.0 if on else 0.0)

    def set_repeat(self, end: int, on: bool) -> bool:
        """At `end` - the project's - go back to 0 and play on, while `on`
        (F-57, D-111). The loop region wins inside it. False when full."""
        return self._send(REPEAT, end, 0, 1.0 if on else 0.0)

    def drain(self) -> None:
        """Apply what is in the ring now. Only for when no stream is running:
        with no audio thread, nothing else can be reading it."""
        self._drain(self._next)

    @property
    def latency(self) -> int:
        """How many frames after its block the engine's output is heard: the
        limiter's lookahead, on or off (D-124)."""
        return LOOKAHEAD

    @property
    def playhead(self) -> int:
        """Where the next block starts."""
        return self._playhead

    def sent(self) -> int:
        """How many commands have been sent: a mark `caught_up` can be
        asked about."""
        return self._written

    def caught_up(self, sent: int) -> bool:
        """Whether the first `sent` commands have all been applied - so the
        playhead read now is after a seek, not before it."""
        return self._read >= sent

    @property
    def playing(self) -> bool:
        return self._playing

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

    def take_channel_peaks(self) -> list[tuple[str, float, float]]:
        """Each channel's highest level on each side since the last time, by
        channel id, and start again (D-117). Read from the snapshot playing,
        so a reorder cannot hand one channel another's level; a block that
        lands between the read and the reset is one frame of a meter."""
        snapshot = self._current
        read = snapshot.peaks.copy()
        snapshot.peaks.fill(0)
        return [
            (lane.channel_id, float(left), float(right))
            for lane, (left, right) in zip(snapshot.lanes, read, strict=True)
        ]

    def _send(
        self,
        kind: float,
        a: float,
        b: float,
        c: float,
        d: float = 0.0,
        e: float = 0.0,
        f: float = 0.0,
    ) -> bool:
        if self._written - self._read >= RING:
            return False
        slot = self._ring[self._written % RING]
        slot[0], slot[1], slot[2], slot[3], slot[4], slot[5], slot[6] = (
            kind,
            a,
            b,
            c,
            d,
            e,
            f,
        )
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
        if self._next_voice is not self._voice:
            # Held as fading before it stops being the voice, so the UI
            # thread never sees it held by neither. One that has finished
            # falls through nothing: `_sound` has no frames left to play.
            self._fading = self._voice
            self._voice = self._next_voice
        self._drain(snapshot)

        bus_l, bus_r = self._bus_l, self._bus_r
        bus_l.fill(0)
        bus_r.fill(0)
        space = snapshot.space
        if self._playing:
            self._mix(snapshot, self._plan())
            if space is not None:
                space.render(snapshot.positions, snapshot.peaks, bus_l, bus_r)
        else:
            # Stopped: nothing ramps, so a gain changed meanwhile is in place
            # when playing starts. The spatial tail still drains, so a pause
            # decays rather than cuts and a resume does not replay it.
            np.copyto(snapshot.levels, snapshot.targets)
            if space is not None:
                space.drain(bus_l, bus_r)
        self._audition()
        self._master(snapshot)

        self._peak(bus_l, 0)
        self._peak(bus_r, 1)
        np.copyto(out[:, 0], bus_l)
        np.copyto(out[:, 1], bus_r)

    def _plan(self) -> int:
        """Cut the block into the pieces of the timeline it plays - one, or
        more where the loop or the repeat wraps - and move the playhead past
        them. How many pieces there are."""
        pieces = self._pieces
        t = self._playhead
        size = self.block
        at = 0
        count = 0
        while at < size:
            length = size - at
            end, back = self._wrap(t)
            if end >= 0 and t + length > end:
                length = end - t
            pieces[count, 0] = t
            pieces[count, 1] = at
            pieces[count, 2] = length
            count += 1
            at += length
            t += length
            if end >= 0 and t >= end:
                t = back
        self._playhead = t
        return count

    def _wrap(self, t: int) -> tuple[int, int]:
        """Where a piece from `t` has to stop, and where the playhead goes
        then: the loop region's end and start, while looping and before its
        end; else the project's end and 0, while repeating and before it
        (D-111); else nowhere, as -1. A playhead already past an end plays
        on. Either span is at least `SHORTEST_LOOP` or never wraps, which
        keeps a block's pieces within `block // SHORTEST_LOOP + 2`."""
        start, end = self._loop_start, self._loop_end
        if self._looping and t < end and end - start >= SHORTEST_LOOP:
            return end, start
        end = self._repeat_end
        if self._repeating and t < end and end >= SHORTEST_LOOP:
            return end, 0
        return -1, 0

    def _mix(self, snapshot: Snapshot, pieces: int) -> None:
        """Every channel's share of the block, at its gain, into the bus."""
        bus_l, bus_r = self._bus_l, self._bus_r
        lane_l, lane_r, lane_m = self._lane_l, self._lane_r, self._lane_m
        targets, levels, peaks = snapshot.targets, snapshot.levels, snapshot.peaks
        lanes = snapshot.lanes
        slots = snapshot.slots
        space = snapshot.space
        if space is not None:
            space.src.fill(0.0)  # a silent spatial channel still has a block
        start = int(self._pieces[0, 0])
        for index in range(len(lanes)):
            now = targets[index]
            was = levels[index]
            if not (now.any() or was.any()):
                continue
            if pieces == 1:
                wrote = fill(lanes[index], start, lane_l, lane_r, lane_m)
            else:
                wrote = self._fill_pieces(lanes[index], pieces)
            if not wrote:
                np.copyto(was, now)
                continue
            # A channel's two sides from its rows and its four factors
            # (D-125): a stereo clip's sides kept or turned down, a mono
            # clip's row added to each at its own factor.
            if wrote & STEREO:
                self._gain(lane_l, lane_l, float(was[2]), float(now[2]), add=False)
                self._gain(lane_r, lane_r, float(was[3]), float(now[3]), add=False)
            if wrote & MONO:
                add = bool(wrote & STEREO)
                self._gain(lane_l, lane_m, float(was[0]), float(now[0]), add=add)
                self._gain(lane_r, lane_m, float(was[1]), float(now[1]), add=add)
            np.copyto(was, now)
            slot = slots[index]
            if space is not None and slot >= 0:
                # A mono point (D-16): the space places it, meters it after
                # its distance, and sums it into the bus after the HRTF.
                row = space.src[slot]
                np.add(lane_l, lane_r, out=row)
                np.multiply(row, 0.5, out=row)
                continue
            # What this channel adds to the bus, for its meter (D-117).
            self._raise(peaks, index, 0, lane_l)
            self._raise(peaks, index, 1, lane_r)
            np.add(bus_l, lane_l, out=bus_l)
            np.add(bus_r, lane_r, out=bus_r)

    def _fill_pieces(self, lane: Lane, pieces: int) -> int:
        """`fill`, a piece at a time, silence in any piece no clip of a row's
        kind plays."""
        self._lane.fill(0)
        wrote = 0
        for piece in range(pieces):
            t, at, length = (int(value) for value in self._pieces[piece])
            wrote |= fill(
                lane,
                t,
                self._lane_l[at : at + length],
                self._lane_r[at : at + length],
                self._lane_m[at : at + length],
            )
        return wrote

    def _gain(
        self,
        into: npt.NDArray[np.float32],
        row: npt.NDArray[np.float32],
        was: float,
        now: float,
        *,
        add: bool,
    ) -> None:
        """`row` at a gain moving from `was` to `now` across the block -
        or held, when they are the same - written into `into`, or added."""
        if was != now:
            ramp = self._ramp
            np.multiply(self._steps, now - was, out=ramp)
            np.add(ramp, was, out=ramp)
            if add:
                np.multiply(row, ramp, out=self._scratch)
                np.add(into, self._scratch, out=into)
            else:
                np.multiply(row, ramp, out=into)
        elif add:
            np.multiply(row, now, out=self._scratch)
            np.add(into, self._scratch, out=into)
        elif now != 1.0 or into is not row:
            np.multiply(row, now, out=into)

    def _master(self, snapshot: Snapshot) -> None:
        """The master gain over the whole bus, ramped, then the limiter
        (D-126, D-123)."""
        was = self._master_level
        now = float(snapshot.master[0])
        if was != now:
            ramp = self._ramp
            np.multiply(self._steps, now - was, out=ramp)
            np.add(ramp, was, out=ramp)
            np.multiply(self._bus_l, ramp, out=self._bus_l)
            np.multiply(self._bus_r, ramp, out=self._bus_r)
            self._master_level = now
        elif now != 1.0:
            np.multiply(self._bus_l, now, out=self._bus_l)
            np.multiply(self._bus_r, now, out=self._bus_r)
        switch = float(snapshot.master[1])
        self._limiter.process(self._bus_l, self._bus_r, self._switch, switch)
        self._switch = switch

    def _audition(self) -> None:
        """The voice's next block, summed into the bus over the channels -
        and a voice just stopped or replaced, falling to silence."""
        fading = self._fading
        if fading is not None:
            self._sound(fading, falling=True)
            self._fading = None
        voice = self._voice
        if voice is not None:
            self._sound(voice, falling=False)

    def _sound(self, voice: Voice, *, falling: bool) -> None:
        read = voice.position
        if read >= voice.frames:
            return
        count = min(self.block, voice.frames - read)
        sample = voice.audio
        into_l = self._bus_l[:count]
        into_r = self._bus_r[:count]
        left = sample[read : read + count, 0]
        right = sample[read : read + count, voice.last]
        if falling:
            fall = self._fall[:count]
            scratch = self._scratch[:count]
            np.multiply(left, fall, out=scratch)
            np.add(into_l, scratch, out=into_l)
            np.multiply(right, fall, out=scratch)
            np.add(into_r, scratch, out=into_r)
        else:
            np.add(into_l, left, out=into_l)
            np.add(into_r, right, out=into_r)
        voice.position = read + count

    def _take_up(self, snapshot: Snapshot) -> None:
        """Start playing `snapshot`, each channel ramping from the gain it
        had in the one before - if the one before is the one it was built
        against. Two installed within one block skip a snapshot, and its
        channels' places mean nothing to this one, so it starts at its
        targets. So does a channel that is new, and so does every channel's
        gain sent after the snapshot was built but before it was taken up:
        its level is its target from the start, not what it was built with.
        The one before is not freed here: whoever installed it still holds
        it."""
        np.copyto(snapshot.levels, snapshot.targets)
        if self._current.generation == 0:
            # The first snapshot: nothing has played, so the master starts
            # where it is rather than ramping there from unity.
            self._master_level = float(snapshot.master[0])
            self._switch = float(snapshot.master[1])
        # The tail is sound already begun: it carries into the new snapshot
        # when the two are shaped alike. The filters do not (05): its first
        # block starts fresh, with no crossfade from a stale one.
        old, new = self._current.space, snapshot.space
        if old is not None and new is not None and old.tail.shape == new.tail.shape:
            np.copyto(new.tail, old.tail)
        del old, new
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
            kind = command[0]
            if kind == GAIN:
                if command[1] == snapshot.generation and 0 <= command[2] < len(targets):
                    sides = targets[int(command[2])]
                    sides[0] = command[3]
                    sides[1] = command[4]
                    sides[2] = command[5]
                    sides[3] = command[6]
            elif kind == SEEK:
                self._playhead = int(command[3])
                if snapshot.space is not None:
                    snapshot.space.fresh = True  # no crossfade from before it
            elif kind == POSITION:
                positions = snapshot.positions
                if command[1] == snapshot.generation and 0 <= command[2] < len(
                    positions
                ):
                    row = int(command[2])
                    positions[row, 0] = command[3]
                    positions[row, 1] = command[4]
                    positions[row, 2] = command[5]
            elif kind == PLAY:
                self._playing = bool(command[3])
            elif kind == LOOP:
                self._loop_start = int(command[1])
                self._loop_end = int(command[2])
                self._looping = bool(command[3])
            elif kind == REPEAT:
                self._repeat_end = int(command[1])
                self._repeating = bool(command[3])
            elif kind == MASTER and command[1] == snapshot.generation:
                snapshot.master[0] = command[2]
                snapshot.master[1] = command[3]
            self._read += 1

    def _peak(self, side: npt.NDArray[np.float32], which: int) -> None:
        np.abs(side, out=self._scratch)
        loudest = self._scratch.max()
        if loudest > self._peaks[which]:
            self._peaks[which] = loudest

    def _raise(
        self,
        peaks: npt.NDArray[np.float64],
        channel: int,
        which: int,
        side: npt.NDArray[np.float32],
    ) -> None:
        """A channel's peak on one side, raised to this block's loudest."""
        np.abs(side, out=self._scratch)
        loudest = self._scratch.max()
        if loudest > peaks[channel, which]:
            peaks[channel, which] = loudest
