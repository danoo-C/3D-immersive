"""The engine's block as Python, as it was before it was compiled (M4 phase
12, D-138): the reference the kernels are held to.

Each function is the package's as it stood at phase 11, with a lane's clip
ends worked out from its clips, which the compiled lane no longer keeps.
Nothing in the package imports this; the kernels are what play.
"""

from __future__ import annotations

import bisect

import numpy as np

from immersive.audio.dsp import Samples
from immersive.audio.scheduler import MONO, STEREO, Lane, Placed


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
