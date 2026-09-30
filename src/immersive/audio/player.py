"""The output: one stream, the transport's, and everything heard goes
through it (D-107).

The player owns the engine and the stream that calls it. The stream opens
the first time anything is to be heard - a Play, or a sample
double-clicked - at 48 kHz with the device and block `settle` chose (D-63),
and stays open until the window closes or the device goes. Audition is a
voice in the same engine, summed into the bus over the arrangement, so a
sample tried during playback is heard against the mix.

**Before the stream has opened there is no audio thread**, so the player
applies the engine's commands itself (`Engine.drain`): a seek or a loop
set before the first Play is in place when it starts.

**A device that goes is noticed on PortAudio's thread and dealt with on the
UI thread.** The stream's `finished_callback` only sets a flag. `poll()`,
which the window calls from its timer, closes what is left of the stream,
stops the transport with the playhead where it was, and reports it once.
Reopening is the next Play or double-click, never a silent move to another
device (05, *The output stream*).

**Every voice handed to the engine is held here** until the engine has let
go of it, as the feed holds snapshots, so a decoded array is never freed
on the audio thread.

Qt-free, like the engine: it reports through a plain callback.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt

from immersive.audio import engine as compiled
from immersive.audio.device import CHANNELS, Output
from immersive.audio.engine import Engine, Voice
from immersive.core.time import SAMPLE_RATE

#: What is said when the device goes.
LOST = "The output device stopped - press Play or double-click a sample to try again"


class Player:
    """The engine, and the one stream it plays on."""

    def __init__(
        self,
        backend: Any,
        output: Output,
        report: Callable[[str], None] | None = None,
    ) -> None:
        self._backend = backend
        self._output = output
        self.report: Callable[[str], None] = report or (lambda _message: None)
        self.engine = Engine(output.block)
        self._stream: Any = None
        #: Set on PortAudio's thread when the stream stops by itself.
        self._lost = False
        self._voices: list[Voice] = []

    # ------------------------------------------------------------ reading

    @property
    def running(self) -> bool:
        """Whether a stream is open and calling the engine."""
        return self._stream is not None

    @property
    def playing(self) -> bool:
        return self.engine.playing

    @property
    def playhead(self) -> int:
        return self.engine.playhead

    @property
    def auditioning(self) -> bool:
        """Whether a sample is being auditioned."""
        return self.engine.auditioning

    # ---------------------------------------------------------- transport

    def play(self) -> bool:
        """Play from the playhead. False if the device would not open."""
        if not self._open():
            return False
        self.engine.set_playing(True)
        return True

    def pause(self) -> None:
        """Stop where it is."""
        self.engine.set_playing(False)
        self._settle()

    def seek(self, sample: int) -> None:
        """Play the next block from `sample`, playing or not."""
        self.engine.seek(max(sample, 0))
        self._settle()

    def set_loop(self, start: int, end: int, on: bool) -> None:
        self.engine.set_loop(start, end, on)
        self._settle()

    def set_repeat(self, end: int, on: bool) -> None:
        """At `end`, the project's, go back to 0 while `on` (D-111)."""
        self.engine.set_repeat(end, on)
        self._settle()

    def audition(self, audio: npt.NDArray[np.float32]) -> bool:
        """Play `audio` from its first frame, over whatever is playing and
        in place of any other audition. False if the device would not open."""
        voice = Voice(audio)
        self._voices.append(voice)
        self.engine.audition(voice)
        self.release()
        return self._open()

    def stop_audition(self) -> None:
        """Silence the audition from the next block, falling rather than cut
        (D-115). The voice is let go of once the engine has."""
        self.engine.audition(None)
        self.release()

    # ------------------------------------------------------------ keeping

    def poll(self) -> None:
        """The UI thread's look at the stream: a device that went is closed
        up, the transport stopped where it was, and said once; voices the
        engine has let go of are let go of here."""
        if self._lost and self._stream is not None:
            self._stream.close()
            self._stream = None
            self.engine.set_playing(False)
            self._settle()
            self.report(LOST)
        self.release()

    def release(self) -> None:
        """Let go of every voice the engine has moved past."""
        engine = self.engine
        self._voices = [voice for voice in self._voices if engine.holds_voice(voice)]

    def close(self) -> None:
        """Close the stream. Not a lost device: `poll` says so only of a
        stream still open."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    # ------------------------------------------------------------ internal

    def _settle(self) -> None:
        """With no stream, nothing drains the ring: apply it here."""
        if self._stream is None:
            self.engine.drain()

    def _open(self) -> bool:
        if self._stream is not None:
            return True
        # The block kernel exists before any stream can call it (D-141): the
        # HRTF worker has usually compiled it, and if not, the first Play
        # after an install waits for it here, before there is an audio
        # thread to miss a block.
        compiled.warm(self._output.block)
        self._lost = False
        try:
            stream = self._backend.OutputStream(
                samplerate=SAMPLE_RATE,
                blocksize=self._output.block,
                device=self._output.device,
                channels=CHANNELS,
                dtype="float32",
                callback=self.engine.callback,
                finished_callback=self._finished,
            )
            stream.start()
        except Exception as failed:  # the backend's own error types
            self.report(f"The output device would not open ({failed})")
            return False
        self._stream = stream
        return True

    def _finished(self) -> None:
        """PortAudio's thread, once the stream has stopped. Only a flag:
        everything else is `poll`'s, on the UI thread, and `poll` looks only
        at a stream still open - so one closed on purpose is not a loss."""
        self._lost = True
