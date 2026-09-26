"""The UI thread's side of the engine: what it is told, and when (D-105).

After every change the document reports, and whenever samples arrive, the
feed looks at the project and tells the engine one of two things:

- **the structure changed** - a clip placed, moved, trimmed or faded, a
  clip's gain, a sample decoded or gone, the channels' order - so it builds
  a new snapshot and hands it over;
- **only how loud a channel is changed** - its gain, mute or solo - so it
  sends each changed channel's new gain through the ring, tagged with the
  snapshot it was worked out against.

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
        tuple(
            (media.id, media.frames, id(decoded) if decoded is not None else None)
            for media in project.media_pool
            for decoded in (audio(media.id),)
        ),
    )


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
        #: Every snapshot handed over that the engine may still read.
        self._held: list[Snapshot] = []

    def update(self, project: Project) -> None:
        """Tell the engine what changed in `project`, if anything did."""
        now = structure(project, self._audio)
        heard = gains(project)
        if self._snapshot is None or now != self._structure:
            self._structure = now
            self._install(project)
        elif heard != self._gains:
            generation = self._snapshot.generation
            for index, (was, gain) in enumerate(zip(self._gains, heard, strict=True)):
                if was != gain and not self._engine.send_gain(generation, index, gain):
                    # The ring is full - nothing is playing to drain it. A
                    # snapshot carries every gain at once instead.
                    self._install(project)
                    break
        self._gains = heard
        self.release()

    def release(self) -> None:
        """Let go of every snapshot the engine has moved past - here, on the
        UI thread, which is the point of holding them."""
        self._held = [held for held in self._held if self._engine.holds(held)]

    def held(self) -> list[Snapshot]:
        return list(self._held)

    def _install(self, project: Project) -> None:
        snapshot = build(project, self._audio, self._snapshot)
        self._held.append(snapshot)
        self._engine.install(snapshot)
        self._snapshot = snapshot
