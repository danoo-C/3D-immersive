"""Preparing the project's HRTF set on a worker (05, *4*; D-116, D-120).

A set is loaded, then decomposed and indexed - 6.5 s cold for SADIE II D1,
0.2 s from the cache - and transformed at the output's block size. Then the
engine's block kernel is compiled, or loaded from numba's cache, so the
audio thread never compiles (D-139, D-141); the player compiles it too if
a Play comes first. None of
that may happen on the UI thread, which it would freeze, nor when a test
merely builds a window: `app.run` asks for it once the window is up, and so
does opening a project whose set is another.

Like the importer, the preparer has a pool of its own, reports how far it
has got fifteen times a second, and can be cancelled: the job stops at its
next chunk, so closing the window does not wait for a decomposition. Every
delivery carries its request's number, so a set asked for and then replaced
is never handed over late.
"""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from immersive.audio import engine
from immersive.audio.hrtf.bank import Bank, prepare
from immersive.audio.hrtf.sofa import builtin
from immersive.core.io.media import Refused
from immersive.core.progress import Cancelled, Progress

#: How often a busy preparer says how far it has got.
REPORTS_PER_SECOND: Final = 15


class _Delivery(QObject):
    """Carries the job's result across threads; parentless, as the
    importer's is, so a job never emits on a deleted object."""

    done = Signal(int, object)  # request, Bank | Refused | Cancelled


class _Job(QRunnable):
    def __init__(
        self,
        request: int,
        set_id: str,
        block: int,
        progress: Progress,
        delivery: _Delivery,
    ) -> None:
        super().__init__()
        self.request = request
        self.set_id = set_id
        self.block = block
        self.progress = progress
        self.delivery = delivery

    def run(self) -> None:
        try:
            hrirs = builtin(self.set_id)
            result: Bank | Refused | Cancelled = (
                hrirs
                if isinstance(hrirs, Refused)
                else prepare(hrirs, self.block, progress=self.progress.part(0.0, 0.9))
            )
            # The engine's block kernel, compiled here or loaded from
            # numba's cache, never on the audio thread (D-139, D-141).
            engine.warm(self.block)
        except Exception as unexpected:  # a job that raised would never deliver
            result = Refused(self.set_id, f"could not be prepared ({unexpected})")
        self.progress.reach(1.0)
        self.delivery.done.emit(self.request, result)


class Preparer(QObject):
    """One set at a time, prepared for one block size."""

    #: The bank is ready.
    prepared = Signal(object)  # Bank
    #: The set could not be had - not fetched, or not usable.
    refused = Signal(object)  # Refused
    #: How far, in thousandths.
    progressed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._delivery = _Delivery()
        self._delivery.done.connect(self._delivered)
        self._request = 0
        self._progress: Progress | None = None
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000 // REPORTS_PER_SECOND)
        self._ticker.timeout.connect(self.report)

    @property
    def busy(self) -> bool:
        return self._progress is not None

    def start(self, set_id: str, block: int) -> None:
        """Prepare `set_id` at `block`, in place of anything under way."""
        self.cancel()
        self._request += 1
        self._progress = Progress()
        self._pool.start(
            _Job(self._request, set_id, block, self._progress, self._delivery)
        )
        self._ticker.start()

    def report(self) -> None:
        if self._progress is not None:
            self.progressed.emit(round(self._progress.done * 1000))

    def cancel(self) -> None:
        """Stop what is under way at its next chunk; nothing is delivered."""
        if self._progress is not None:
            self._progress.cancelled = True
        self._progress = None
        self._ticker.stop()

    def _delivered(self, request: int, result: object) -> None:
        if request != self._request or self._progress is None:
            return  # a request since replaced or cancelled
        self._progress = None
        self._ticker.stop()
        if isinstance(result, Bank):
            self.prepared.emit(result)
        elif isinstance(result, Refused):
            self.refused.emit(result)
