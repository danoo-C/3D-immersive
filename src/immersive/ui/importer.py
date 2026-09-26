"""Preparing samples on workers, and handing them back on the UI thread.

02's threading table: workers decode, resample and build peaks, and never
touch a widget or the model. So a job is handed a path and returns a value,
and the value reaches the UI thread by a queued signal - the only place the
model is edited from. N-3 is the reason: a folder of forty samples decoded on
the UI thread is a window frozen for as long as that takes.

**How far a batch has got** (F-59). Each file has a `core.progress.Progress`
its worker moves as it reads; the importer reads them fifteen times a second
while busy and says so by `progressed`, weighting each file by its size, so
the window's activity moves with the bytes rather than jumping as files end
(D-113). **A batch can be cancelled** (D-114): the queue is cleared, every
running file is asked to stop at its next chunk, and nothing is delivered.
Every delivery carries its batch's number, so a file that finishes after its
batch was dropped is not counted in the next.

The pool is the importer's own, so clearing its queue touches nothing else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from immersive.core.io.media import Refused
from immersive.core.media_store import Prepared, prepare
from immersive.core.progress import Cancelled, Progress

#: How often a busy importer says how far it has got.
REPORTS_PER_SECOND: Final = 15


class _Delivery(QObject):
    """Carries one job's result across threads.

    Parentless and referenced by every job, so it lives until the last job
    has delivered - even if the importer that started them is gone - and a
    worker never emits on a deleted object.
    """

    prepared = Signal(int, int, object)  # batch, index, result


class _Job(QRunnable):
    def __init__(
        self,
        batch: int,
        index: int,
        path: Path,
        progress: Progress,
        delivery: _Delivery,
    ) -> None:
        super().__init__()
        self.batch = batch
        self.index = index
        self.path = path
        self.progress = progress
        self.delivery = delivery

    def run(self) -> None:
        # `prepare` reports rather than raises, but a job that did raise
        # would never deliver, and the import would wait for it forever.
        try:
            result: Prepared | Refused | Cancelled = prepare(
                self.path, None, self.progress
            )
        except Exception as unexpected:
            result = Refused(str(self.path), f"could not be imported ({unexpected})")
        self.delivery.prepared.emit(self.batch, self.index, result)


def _size(path: Path) -> int:
    """A file's weight in the batch: its bytes, and at least one."""
    try:
        return max(path.stat().st_size, 1)
    except OSError:
        return 1


class Importer(QObject):
    """Prepares a batch of files in parallel, and says when all are in.

    One batch at a time: the window asks `busy` before starting another.
    Results come back in the order the paths were given, whatever order the
    workers finished in, so the pool's order does not depend on scheduling.
    """

    finished = Signal(object)  # list[Prepared | Refused], in path order
    #: The batch was dropped by `cancel()`: nothing will be delivered.
    cancelled = Signal()
    #: Files done, files in all, bytes done, bytes in all.
    progressed = Signal(int, int, int, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._delivery = _Delivery()
        self._delivery.prepared.connect(self._delivered)
        self._batch = 0
        self._results: list[Prepared | Refused | None] = []
        self._progress: list[Progress] = []
        self._sizes: list[int] = []
        self._outstanding = 0
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000 // REPORTS_PER_SECOND)
        self._ticker.timeout.connect(self.report)

    @property
    def busy(self) -> bool:
        return self._outstanding > 0

    def start(self, paths: list[Path]) -> None:
        if self.busy:
            raise RuntimeError("an import is already running")
        if not paths:
            self.finished.emit([])
            return
        self._batch += 1
        self._results = [None] * len(paths)
        self._progress = [Progress() for _ in paths]
        self._sizes = [_size(path) for path in paths]
        self._outstanding = len(paths)
        for index, path in enumerate(paths):
            self._pool.start(
                _Job(self._batch, index, path, self._progress[index], self._delivery)
            )
        self._ticker.start()

    def progress(self) -> tuple[int, int, int, int]:
        """Files done, files in all, bytes done and bytes in all, now."""
        files = len(self._sizes)
        done = 0.0
        for size, progress, result in zip(
            self._sizes, self._progress, self._results, strict=True
        ):
            done += size * (1.0 if result is not None else progress.done)
        return files - self._outstanding, files, round(done), sum(self._sizes)

    def report(self) -> None:
        self.progressed.emit(*self.progress())

    def cancel(self) -> None:
        """Drop the batch: nothing queued starts, each running file stops at
        its next chunk, and nothing is delivered. Says so by `cancelled`."""
        if not self.busy:
            return
        self._pool.clear()
        for progress in self._progress:
            progress.cancelled = True
        self._forget()
        self.cancelled.emit()

    def _delivered(self, batch: int, index: int, result: object) -> None:
        if batch != self._batch or not self.busy:
            return  # from a batch since dropped
        assert isinstance(result, (Prepared, Refused)), result
        self._results[index] = result
        self._outstanding -= 1
        if self._outstanding == 0:
            done = [each for each in self._results if each is not None]
            self.report()
            self._forget()
            self.finished.emit(done)

    def _forget(self) -> None:
        self._ticker.stop()
        self._outstanding = 0
        self._results = []
        self._progress = []
        self._sizes = []
