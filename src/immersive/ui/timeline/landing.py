"""Where a drop from the media pool lands, and the one command it makes.

Qt-free, like the grid and the time axis: the view turns a drag into a
position and two modifiers, and everything about what that means is here,
tested without a window.

- **The lane** is the one under the pointer; below the last, the drop makes
  a new channel (04, *Media pool*).
- **The start** is the sample under the pointer, snapped to the grid and to
  every clip's edges on any channel (F-13, F-17), by the target channel's
  own snap setting (F-18) - or exactly under the pointer while `Alt` is held.
- **Several samples** go end to end from there, in the order the pool lists
  them; below the last lane, one new channel holds them all.
- **An overlap** is settled by `DropClips` (D-95) - unless Shift is held,
  which refuses it instead (03, *Rules*).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from immersive.core.commands import Command, Compound
from immersive.core.edits import AddChannel, DropClips
from immersive.core.model import (
    CLIP_PREFIX,
    Clip,
    MediaFile,
    Project,
    all_ids,
    effective_snap,
    mint_id,
    new_channel,
)
from immersive.core.time import snap
from immersive.ui.timeline.metrics import LANE_HEIGHT


@dataclass(frozen=True)
class Landing:
    """Where each dropped sample would start, and whether it may."""

    #: The channel's index - or the channel count, for a new one.
    lane: int
    #: Each sample, and the sample it starts at on the timeline.
    placed: tuple[tuple[MediaFile, int], ...]
    #: Below the last lane: the drop makes the channel it lands on.
    creates: bool
    #: Shift was held over an occupied span, so the drop is refused.
    refused: bool

    @property
    def start(self) -> int:
        return self.placed[0][1]

    @property
    def end(self) -> int:
        sample, start = self.placed[-1]
        return start + sample.frames


def edges(project: Project) -> list[int]:
    """Every clip's start and end, on any channel, sorted - what a drop may
    snap to besides the grid (F-17)."""
    return sorted(
        {
            edge
            for channel in project.channels
            for clip in channel.clips
            for edge in (clip.start, clip.end)
        }
    )


def landing(
    project: Project,
    media_ids: Sequence[str],
    x: float,
    y: float,
    scale: float,
    *,
    exact: bool = False,
    refuse_overlap: bool = False,
) -> Landing | None:
    """Where `media_ids`, dropped at scene `(x, y)`, would land at `scale`.

    `None` when nothing dropped is a sample the project has - a drag from
    somewhere else, or of samples an Undo has since taken away.
    """
    known = {media.id: media for media in project.media_pool}
    samples = [known[i] for i in media_ids if i in known and known[i].frames > 0]
    if not samples:
        return None

    channels = project.channels
    lane = max(int(y // LANE_HEIGHT), 0)
    creates = lane >= len(channels)
    lane = min(lane, len(channels))

    start = max(round(x * scale), 0)
    if not exact:
        setting = project.snap if creates else effective_snap(project, channels[lane])
        start = snap(
            start,
            bpm=project.bpm,
            time_signature=project.time_signature,
            division=setting.division if setting.enabled else None,
            triplet=setting.triplet,
            edges=edges(project),
        )

    placed = []
    at = start
    for sample in samples:
        placed.append((sample, at))
        at += sample.frames
    overlaps = not creates and any(
        clip.start < at and start < clip.end for clip in channels[lane].clips
    )
    return Landing(lane, tuple(placed), creates, refused=refuse_overlap and overlaps)


def dropped(project: Project, where: Landing, palette: Sequence[str]) -> Command:
    """The one command a drop pushes: its clips placed, and below the last
    lane the channel they are placed on, so one Undo takes back both."""
    taken = all_ids(project)
    clips = []
    for sample, start in where.placed:
        clip_id = mint_id(CLIP_PREFIX, taken)
        taken.add(clip_id)
        clips.append(Clip(clip_id, sample.id, start, 0, sample.frames))
    if where.creates:
        channel = new_channel(project, palette)
        return Compound(
            [AddChannel(project, channel), DropClips(project, channel, clips)]
        )
    return DropClips(project, project.channels[where.lane], clips)
