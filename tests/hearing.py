"""Hearing an engine: blocks played, and read back as the timeline they
played, with the engine's latency taken off as a render takes it off
(D-124). Sample `n` of what is read is the `n`th the engine was asked for
since the first block, wherever the lookahead put it in the output."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from immersive.audio.engine import Engine
from immersive.audio.limiter import LOOKAHEAD
from standin import Stream

Audio = npt.NDArray[np.float32]


class Tape:
    """An engine, or the stand-in stream a player drives one through, played
    block by block, then read back. A read plays on as far as the latency
    still holds back, so a test reads after the last thing it does."""

    def __init__(self, source: Engine | Stream) -> None:
        self._play: Callable[[], Audio]
        if isinstance(source, Engine):
            out = np.zeros((source.block, 2), dtype=np.float32)

            def process() -> Audio:
                source.process(out)
                return out.copy()

            self._play = process
            self._size = source.block
            self._latency = source.latency
        else:
            self._play = source.block
            self._size = int(source.settings["blocksize"])
            self._latency = LOOKAHEAD
        self._blocks: list[Audio] = []

    def play(self, blocks: int = 1) -> None:
        for _ in range(blocks):
            self._blocks.append(self._play())

    def heard(self, first: int = 0, count: int | None = None) -> Audio:
        """Blocks `first` to `first + count` of what was played - from
        `first` to the last played, by default - `(frames, 2)`."""
        size = self._size
        if count is None:
            count = len(self._blocks) - first
        start = first * size + self._latency
        stop = start + count * size
        while len(self._blocks) * size < stop:
            self.play()
        return np.concatenate(self._blocks)[start:stop]


def listen(source: Engine | Stream, blocks: int = 1) -> Audio:
    """The next `blocks` blocks played, from where it is."""
    tape = Tape(source)
    tape.play(blocks)
    return tape.heard()
