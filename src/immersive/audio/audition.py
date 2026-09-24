"""Audition: one sample, straight to the output, no spatialisation (F-8).

Deliberately trivial, as the roadmap asks. The engine, its snapshots and the
realtime rules for thirty-two sources are M3's and M4's; this plays one
decoded sample from its first frame to its last and stops.

**Replacing what is playing is one reference swap.** The callback reads
`self._source` once per block, and a new double-click assigns a new one - an
attribute assignment, atomic under the GIL - so the next block is the new
sample's first. The stream is reopened only if it has stopped or is about to,
and the order of three flag operations below is what makes "about to"
decidable without a lock: see `_callback` and `play`.

Qt-free (see `device.py`). Problems are reported through a plain callback the
window supplies, which must itself be safe to call from PortAudio's thread.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from immersive.audio.device import CHANNELS, Output
from immersive.core.time import SAMPLE_RATE

Audio = npt.NDArray[np.float32]


@dataclass
class _Source:
    """A sample and how far through it the callback is. The position is only
    ever written by the callback thread."""

    audio: Audio
    position: int = 0


class Audition:
    """Plays decoded samples on the output `settle` chose."""

    def __init__(
        self,
        backend: Any,
        output: Output,
        report: Callable[[str], None] | None = None,
    ) -> None:
        self._backend = backend
        self._output = output
        self.report: Callable[[str], None] = report or (lambda _message: None)
        self._stream: Any = None
        self._source: _Source | None = None
        #: Set by the callback just before it decides whether to stop, and
        #: cleared if it finds a new sample instead. See `play`.
        self._stopping = False
        self._closing = False

    # ---------------------------------------------------------------- the UI

    def play(self, audio: Audio) -> None:
        """Play `audio` from its first frame, replacing whatever is playing."""
        self._source = _Source(audio)
        # Read *after* the swap. The callback sets `_stopping` *before* it
        # checks whether the source changed, so either it sees the new source
        # and carries on, or this sees `_stopping` and reopens - there is no
        # order of the two threads in which the new sample is lost.
        if self._stream is None or self._stopping:
            self._open()

    def stop(self) -> None:
        self._source = None

    def close(self) -> None:
        self._closing = True
        self._source = None
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    # ----------------------------------------------------------- the stream

    def _open(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._stopping = False
        try:
            stream = self._backend.OutputStream(
                samplerate=SAMPLE_RATE,
                blocksize=self._output.block,
                device=self._output.device,
                channels=CHANNELS,
                dtype="float32",
                callback=self._callback,
                finished_callback=self._finished,
            )
            stream.start()
        except Exception as failed:  # the backend's own error types
            self._source = None
            self.report(f"The output device would not open ({failed})")
            return
        self._stream = stream

    def _callback(self, outdata: Audio, frames: int, time: Any, status: Any) -> None:
        """PortAudio's thread. Copies the next block; silence past the end.

        A mono sample goes to both ears. Nothing here allocates beyond the
        slice views, and nothing here touches the model or a widget.
        """
        source = self._source
        if source is None:
            outdata.fill(0)
            self._stop_unless_replaced(None)
            return
        start = source.position
        end = min(start + frames, len(source.audio))
        count = end - start
        block = source.audio[start:end]
        if block.shape[1] == 1:
            outdata[:count, 0] = block[:, 0]
            outdata[:count, 1] = block[:, 0]
        else:
            outdata[:count] = block
        outdata[count:] = 0
        source.position = end
        if end >= len(source.audio):
            self._stop_unless_replaced(source)

    def _stop_unless_replaced(self, finished: _Source | None) -> None:
        # Announce first, then look: see `play` for why this order matters.
        self._stopping = True
        if self._source is not finished:
            self._stopping = False
            return
        self._source = None
        raise self._backend.CallbackStop

    def _finished(self) -> None:
        """PortAudio's thread, once the stream has stopped for any reason.

        Stopping at the end of a sample is expected; stopping otherwise means
        the device went - headphones pulled, an interface switched off - and
        05 says that is reported and reopening is the person's to do.
        """
        if not self._stopping and not self._closing:
            self._source = None
            self.report(
                "The output device stopped - double-click a sample to try again"
            )
        self._stopping = True
