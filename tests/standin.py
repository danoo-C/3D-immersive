"""A stand-in for `sounddevice`, for tests that need a stream and no device.

It implements only what `sounddevice`'s documentation promises and the
player uses: `OutputStream`'s arguments, the callback's signature, the
`finished_callback`, and `CallbackStop`. A test runs the callback one block
at a time with `Stream.block()`. Whether the real thing sounds right is a
person's to say, on native Windows or Linux.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt


class CallbackStop(Exception):
    """sounddevice.CallbackStop's stand-in."""


@dataclass
class Status:
    """`sounddevice.CallbackFlags`'s one attribute the engine reads."""

    output_underflow: bool = False


class Stream:
    """sounddevice.OutputStream's stand-in: records how it was opened and lets
    a test run its callback one block at a time."""

    def __init__(self, backend: Backend, **settings: Any) -> None:
        self.settings = settings
        self.callback: Callable[..., None] = settings["callback"]
        self.finished: Callable[[], None] = settings["finished_callback"]
        self.active = False
        self.closed = False
        backend.streams.append(self)

    def start(self) -> None:
        self.active = True

    def close(self) -> None:
        self.closed = True
        self.active = False

    def block(self, status: Status | None = None) -> npt.NDArray[np.float32]:
        """Run the callback once, as PortAudio would, and return what it wrote."""
        out = np.full((self.settings["blocksize"], 2), np.nan, dtype=np.float32)
        try:
            self.callback(out, self.settings["blocksize"], None, status or Status())
        except CallbackStop:
            self.active = False
            self.finished()
        return out

    def lose(self) -> None:
        """What PortAudio does when the device goes: stop, and say so, without
        anyone having raised `CallbackStop`."""
        self.active = False
        self.finished()


class Backend:
    CallbackStop = CallbackStop

    def __init__(self, refuse: bool = False) -> None:
        self.streams: list[Stream] = []
        self.refuse = refuse

    def OutputStream(self, **settings: Any) -> Stream:
        if self.refuse:
            raise RuntimeError("Device unavailable")
        return Stream(self, **settings)


def ramp(frames: int, channels: int = 1) -> npt.NDArray[np.float32]:
    """Every frame different, so order and position are visible."""
    values = (np.arange(frames, dtype=np.float32) + 1) / (frames + 1)
    return np.ascontiguousarray(np.repeat(values[:, None], channels, axis=1))
