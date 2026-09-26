"""What Copy and Cut took, to be pasted back into the same project (D-99).

**Copies, not the clips.** A paste is what was copied, not what the clips
have become since: moving, trimming or deleting an original after Copy
changes nothing that pastes. Each copy is held with its lane counted from
the topmost copied clip's and its start from the earliest's, which is the
shape a paste keeps (D-100).

**The open project's.** Owned by the `Document` beside the selection, and
emptied when the project is replaced. A clip names its sample by id, and an
id means something only in the project that minted it. The one way a sample
leaves the pool is an Undo of its import, and a clipboard naming one that
has gone cannot be pasted at all - not in part, which would drop material
without a word.

Not the system clipboard: nothing outside the application reads clips.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from immersive.core.model import Channel, Clip, Project
from immersive.core.selection import lane_of


class Clipboard:
    """Copies of clips, each with its lane counted from the topmost and its
    start from the earliest - in lane order, then time order."""

    def __init__(self) -> None:
        self._held: list[tuple[int, Clip]] = []
        #: The channel the topmost copied clips came from, by identity: where
        #: a paste goes when no channel is focused (D-100).
        self._source: Channel | None = None

    def __bool__(self) -> bool:
        return bool(self._held)

    def held(self) -> list[tuple[int, Clip]]:
        """What a paste lands: each copy's lane, counted from the topmost,
        and the copy, its start counted from the earliest."""
        return list(self._held)

    def hold(self, project: Project, clips: Sequence[Clip]) -> None:
        """Copies of `clips`, in place of whatever was held."""
        if not clips:
            self.clear()
            return
        placed = sorted(
            ((lane_of(project, clip), clip) for clip in clips),
            key=lambda pair: (pair[0], pair[1].start),
        )
        top = placed[0][0]
        earliest = min(clip.start for clip in clips)
        self._held = [
            (
                lane - top,
                replace(
                    clip,
                    start=clip.start - earliest,
                    fade_in=replace(clip.fade_in),
                    fade_out=replace(clip.fade_out),
                ),
            )
            for lane, clip in placed
        ]
        self._source = project.channels[top]

    def clear(self) -> None:
        self._held = []
        self._source = None

    def missing(self, project: Project) -> list[str]:
        """The ids of the samples copied clips play that are no longer in
        `project`'s pool, sorted."""
        pool = {media.id for media in project.media_pool}
        return sorted({clip.media_id for _, clip in self._held} - pool)

    def pastable(self, project: Project) -> bool:
        """Whether there is anything to paste, and all of it can be."""
        return bool(self._held) and not self.missing(project)

    def lane(self, project: Project, focused: Channel | None) -> int:
        """Which lane the topmost copied clips land on (D-100): the focused
        channel's; with none, the one they were copied from, while it is
        still in the project; and the first otherwise."""
        for wanted in (focused, self._source):
            for index, channel in enumerate(project.channels):
                if wanted is not None and channel is wanted:
                    return index
        return 0
