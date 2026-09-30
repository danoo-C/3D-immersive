"""The spatial path as Python, as it was before it was compiled (M4 phase
11, D-138): the reference the kernel is held to.

`render(space, ...)` is `Space.render` as it stood at phase 10, method for
method, with `self` become `space`. The scratch buffers it needed and the
kernel does not are made here, once a space, and kept beside it. Nothing
in the package imports this; the kernel is what plays.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import numpy.typing as npt

from immersive.audio.hrtf.lookup import Lookup
from immersive.audio.spatial import AHEAD, HALF_POWER, PAIR_CAP, POINT, Space

Samples = npt.NDArray[np.float32]

_scratch: dict[int, SimpleNamespace] = {}


def scratch(space: Space) -> SimpleNamespace:
    """What the Python render wrote besides the space's own arrays."""
    made = _scratch.get(id(space))
    if made is None or made.space is not space:
        count = space.count
        bins = space.bank.nfft // 2 + 1
        made = SimpleNamespace(
            space=space,
            directions=np.zeros((count, 3)),
            evening=np.zeros((count, 3)),
            product=np.zeros((count, bins), dtype=np.complex64),
            half=np.zeros(bins, dtype=np.complex64),
            ramp=np.zeros(space.block, dtype=np.float32),
            scratch=np.zeros(space.block, dtype=np.float32),
            angle=np.zeros(bins, dtype=np.float32),
            gather=np.zeros(bins, dtype=np.complex64),
            weighed=np.zeros((4, bins), dtype=np.complex64),
            cross=np.zeros((2, bins), dtype=np.complex64),
        )
        _scratch[id(space)] = made
    return made


def render(
    space: Space,
    positions: npt.NDArray[np.float64],
    peaks: npt.NDArray[np.float64],
    bus_l: Samples,
    bus_r: Samples,
) -> None:
    """Every source's `src`, placed, summed into the bus."""
    own = scratch(space)
    count = space.count
    src = space.src
    sides = space.sides
    for slot in range(count):
        (x, y, z), gain, reach = _placed(
            space, positions, space.channels[slot], max(sides[slot], 0)
        )
        own.directions[slot, 0] = x
        own.directions[slot, 1] = y
        own.directions[slot, 2] = z
        space.reach[slot] = reach
        space.target[slot] = gain

    bank = space.bank
    bank.lookup.weigh(own.directions, space.vertices, space.weights, count)
    Lookup.blend(bank.itd, space.vertices, space.weights, space.itds, count)
    if space.keep_level:
        np.take(bank.evening, space.vertices, out=own.evening)
        np.multiply(space.weights, own.evening, out=space.loudness)
    for slot in range(count):
        _filter(space, slot)
    if space.pairs:
        _pair_gains(space)

    for slot in range(count):
        channel = space.channels[slot]
        row = src[slot]
        gain = float(space.target[slot])
        level = gain if space.fresh else float(space.distance[slot])
        if level != gain:
            np.multiply(space.steps, gain - level, out=own.ramp)
            np.add(own.ramp, level, out=own.ramp)
            np.multiply(row, own.ramp, out=row)
        elif gain != 1.0:
            np.multiply(row, gain, out=row)
        space.distance[slot] = gain
        np.abs(row, out=own.scratch)
        loudest = float(own.scratch.max())
        side = sides[slot]
        for which in (0, 1) if side == POINT else (side,):
            if loudest > peaks[channel, which]:
                peaks[channel, which] = loudest

    if space.fresh or not space.crossfade:
        np.copyto(space.previous_left, space.left)
        np.copyto(space.previous_right, space.right)
        space.fresh = False

    block = space.block
    windowed = space.windowed
    for slot in range(count):
        np.multiply(src[slot], space.fade_out, out=windowed[slot, :block])
        np.multiply(src[slot], space.fade_in, out=windowed[count + slot, :block])
    np.fft.rfft(windowed, axis=1, norm="ortho", out=space.spectra)  # type: ignore[arg-type]
    fading_out = space.spectra[:count]
    fading_in = space.spectra[count:]
    for ear, (was, now) in enumerate(
        ((space.previous_left, space.left), (space.previous_right, space.right))
    ):
        np.multiply(fading_out, was, out=own.product)
        np.sum(own.product, axis=0, out=space.total[ear])
        np.multiply(fading_in, now, out=own.product)
        np.sum(own.product, axis=0, out=own.half)
        np.add(space.total[ear], own.half, out=space.total[ear])
    np.fft.irfft(space.total, n=bank.nfft, axis=1, norm="ortho", out=space.inverse)  # type: ignore[arg-type]
    np.add(space.tail, space.inverse, out=space.tail)
    drain(space, bus_l, bus_r)
    np.copyto(space.previous_left, space.left)
    np.copyto(space.previous_right, space.right)


def _placed(
    space: Space, positions: npt.NDArray[np.float64], channel: int, side: int
) -> tuple[tuple[float, float, float], float, float]:
    x = float(positions[channel, side, 0])
    y = float(positions[channel, side, 1])
    z = float(positions[channel, side, 2])
    r = math.sqrt(x * x + y * y + z * z)
    direction = AHEAD if r == 0.0 else (x / r, y / r, z / r)
    nearest = space.min_distance
    if space.keep_level:
        nearest = max(nearest, space.ref_distance)
    gain = (space.ref_distance / max(r, nearest)) ** space.rolloff
    reach = min(r / space.min_distance, 1.0) if space.min_distance > 0.0 else 1.0
    return direction, gain, reach


def _filter(space: Space, slot: int) -> None:
    own = scratch(space)
    filters = space.bank.filters
    vertices = space.vertices
    weights = space.loudness if space.keep_level else space.weights
    reach = float(space.reach[slot])
    left, right = space.left[slot], space.right[slot]
    for ear, out in ((0, left), (1, right)):
        np.multiply(filters[vertices[slot, 0], ear], float(weights[slot, 0]), out=out)
        for corner in (1, 2):
            np.multiply(
                filters[vertices[slot, corner], ear],
                float(weights[slot, corner]),
                out=own.gather,
            )
            np.add(out, own.gather, out=out)
        if reach < 1.0:
            np.multiply(out, reach, out=out)
    itd = float(space.itds[slot]) * reach
    far = left if itd > 0.0 else right
    if itd != 0.0:
        _delay(space, abs(itd))
        np.multiply(far, space.delay, out=far)
    if reach < 1.0:
        flat = 1.0 - reach
        side = space.sides[slot]
        whole = round(abs(itd))
        for ear, row in ((0, left), (1, right)):
            if side != POINT and side != ear:
                continue
            if row is far and whole != 0:
                _delay(space, whole)
                np.multiply(space.delay, flat, out=own.gather)
                np.add(row, own.gather, out=row)
            else:
                np.add(row, flat, out=row)


def _pair_gains(space: Space) -> None:
    own = scratch(space)
    weighed, cross = own.weighed, own.cross
    for index, (first, second) in enumerate(space.pairs):
        if space.keep_level:
            mine, other = space.pair_left[index], space.pair_right[index]
            np.multiply(space.left[first], mine, out=weighed[0])
            np.multiply(space.right[first], mine, out=weighed[1])
            np.multiply(space.left[second], other, out=weighed[2])
            np.multiply(space.right[second], other, out=weighed[3])
            np.conjugate(space.left[second], out=cross[0])
            np.multiply(space.left[first], cross[0], out=cross[0])
            np.conjugate(space.right[second], out=cross[1])
            np.multiply(space.right[first], cross[1], out=cross[1])
            np.add(cross[0], cross[1], out=cross[0])
            loud = (
                float(np.vdot(weighed[0], weighed[0]).real)
                + float(np.vdot(weighed[1], weighed[1]).real)
                + float(np.vdot(weighed[2], weighed[2]).real)
                + float(np.vdot(weighed[3], weighed[3]).real)
                + float(np.vdot(space.pair_shared[index], cross[0]).real)
            )
            gain = PAIR_CAP if loud <= 1.0 / PAIR_CAP**2 else 1.0 / math.sqrt(loud)
        else:
            gain = HALF_POWER
        space.target[first] *= gain
        space.target[second] *= gain


def _delay(space: Space, samples: float) -> None:
    own = scratch(space)
    np.multiply(space.bins_, -2.0 * math.pi * samples / space.bank.nfft, out=own.angle)
    np.cos(own.angle, out=space.delay.real)
    np.sin(own.angle, out=space.delay.imag)


def drain(space: Space, bus_l: Samples, bus_r: Samples) -> None:
    """The accumulator's next block into the bus, and the rest moved up
    a block: what a stopped transport still does, so a pause decays
    rather than cuts, and a resume does not replay it."""
    block = space.block
    tail = space.tail
    np.add(bus_l, tail[0, :block], out=bus_l)
    np.add(bus_r, tail[1, :block], out=bus_r)
    keep = tail.shape[1] - block
    np.copyto(space.shifted[:, :keep], tail[:, block:])
    np.copyto(tail[:, :keep], space.shifted[:, :keep])
    tail[:, keep:].fill(0.0)
