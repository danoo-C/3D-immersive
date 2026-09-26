"""The UI thread's side of the engine: what it is told, and when (D-105).

After every change the document reports, and whenever samples arrive, the
feed looks at the project and tells the engine one of two things:

- **the structure changed** - a clip placed, moved, trimmed or faded, a
  clip's gain, a sample decoded or gone, the channels' order - so it builds
  a new snapshot and hands it over;
- **only how loud a channel is, or where it is, changed** - its gain, mute
  or solo, or its position - so it sends each changed channel's new gain
  or position through the ring, tagged with the snapshot it was worked out
  against (D-105, D-121).

Whether a channel is bypassed, the distance settings and the HRTF bank are
structure: they reshape what a block does, and change rarely. The bank
arrives from the window through `set_bank`, once it is prepared.

**It keeps every snapshot it has handed over** until the engine has moved
past it, and lets go of them itself, here, on the UI thread. The engine
never holds the only reference, so the arrays of a snapshot nobody plays
any more are never freed on the audio thread.

Qt-free: phase 9 connects it to the window; here it answers to a
`Document`, or to anything that calls `update`.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable

from immersive.audio.engine import Engine
from immersive.audio.hrtf.bank import Bank
from immersive.audio.scheduler import Snapshot, build, gains
from immersive.core.io.media import Decoded
from immersive.core.model import Project


def structure(project: Project, audio: Callable[[str], Decoded | None]) -> Hashable:
    """Everything a snapshot is built from except the channels' gains: when
    this is unchanged, a new snapshot would play exactly as the old one."""
    return (
        tuple(
            (
                channel.id,
                tuple(
                    (
                        clip.start,
                        clip.offset,
                        clip.length,
                        clip.media_id,
                        clip.gain_db,
                        clip.fade_in.length,
                        clip.fade_in.shape,
                        clip.fade_out.length,
                        clip.fade_out.shape,
                    )
                    for clip in channel.clips
                ),
            )
            for channel in project.channels
        ),
        tuple(channel.hrtf_bypass for channel in project.channels),
        (
            project.distance.rolloff,
            project.distance.min_distance,
            project.distance.ref_distance,
        ),
        tuple(
            (media.id, media.frames, id(decoded) if decoded is not None else None)
            for media in project.media_pool
            for decoded in (audio(media.id),)
        ),
    )


def positions(project: Project) -> list[tuple[float, float, float]]:
    """Each channel's position, metres, in the order of its lane."""
    return [(c.position.x, c.position.y, c.position.z) for c in project.channels]


class Feed:
    """What the engine plays, kept in step with a project."""

    def __init__(self, engine: Engine, audio: Callable[[str], Decoded | None]) -> None:
        self._engine = engine
        self._audio = audio
        #: The snapshot handed over last, what it was built from, and the
        #: gains the engine has been sent since.
        self._snapshot: Snapshot | None = None
        self._structure: Hashable = None
        self._gains: list[float] = []
        self._positions: list[tuple[float, float, float]] = []
        #: The HRTF bank, once the window has one (D-120).
        self._bank: Bank | None = None
        self._project: Project | None = None
        #: Every snapshot handed over that the engine may still read.
        self._held: list[Snapshot] = []

    def update(self, project: Project) -> None:
        """Tell the engine what changed in `project`, if anything did."""
        self._project = project
        now = structure(project, self._audio)
        heard = gains(project)
        placed = positions(project)
        if self._snapshot is None or now != self._structure:
            self._structure = now
            self._install(project)
        elif not self._sent(heard, placed):
            # The ring is full - nothing is playing to drain it. A snapshot
            # carries every gain and position at once instead.
            self._install(project)
        self._gains = heard
        self._positions = placed
        self.release()

    def set_bank(self, bank: Bank | None) -> None:
        """Play the project through `bank` from the next snapshot: every
        channel not bypassed is heard from where it is."""
        self._bank = bank
        if self._project is not None:
            self._structure = structure(self._project, self._audio)
            self._install(self._project)
            self.release()

    def _sent(
        self, heard: list[float], placed: list[tuple[float, float, float]]
    ) -> bool:
        """Each changed gain and position through the ring. False as soon
        as the ring is full."""
        assert self._snapshot is not None
        generation = self._snapshot.generation
        engine = self._engine
        for index, (was, gain) in enumerate(zip(self._gains, heard, strict=True)):
            if was != gain and not engine.send_gain(generation, index, gain):
                return False
        for index, (before, where) in enumerate(
            zip(self._positions, placed, strict=True)
        ):
            if before != where and not engine.send_position(generation, index, *where):
                return False
        return True

    def release(self) -> None:
        """Let go of every snapshot the engine has moved past - here, on the
        UI thread, which is the point of holding them."""
        self._held = [held for held in self._held if self._engine.holds(held)]

    def held(self) -> list[Snapshot]:
        return list(self._held)

    def _install(self, project: Project) -> None:
        snapshot = build(project, self._audio, self._snapshot, self._bank)
        self._held.append(snapshot)
        self._engine.install(snapshot)
        self._snapshot = snapshot
