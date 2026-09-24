"""Preparing samples on workers, and handing them back on the UI thread.

02's threading table: workers decode, resample and build peaks, and never
touch a widget or the model. So a job is handed a path and returns a value,
and the value reaches the UI thread by a queued signal - the only place the
model is edited from. N-3 is the reason: a folder of forty samples decoded on
the UI thread is a window frozen for as long as that takes.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from immersive.core.io.media import Refused
from immersive.core.media_store import Prepared, prepare


class _Delivery(QObject):
    """Carries one job's result across threads.

    Parentless and referenced by every job, so it lives until the last job
    has delivered - even if the importer that started them is gone - and a
    worker never emits on a deleted object.
    """

    prepared = Signal(int, object)


class _Job(QRunnable):
    def __init__(self, index: int, path: Path, delivery: _Delivery) -> None:
        super().__init__()
        self.index = index
        self.path = path
        self.delivery = delivery

    def run(self) -> None:
        # `prepare` reports rather than raises, but a job that did raise
        # would never deliver, and the import would wait for it forever.
        try:
            result: Prepared | Refused = prepare(self.path)
        except Exception as unexpected:
            result = Refused(str(self.path), f"could not be imported ({unexpected})")
        self.delivery.prepared.emit(self.index, result)


class Importer(QObject):
    """Prepares a batch of files in parallel, and says when all are in.

    One batch at a time: the window asks `busy` before starting another.
    Results come back in the order the paths were given, whatever order the
    workers finished in, so the pool's order does not depend on scheduling.
    """

    finished = Signal(object)  # list[Prepared | Refused], in path order

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._delivery = _Delivery()
        self._delivery.prepared.connect(self._delivered)
        self._results: list[Prepared | Refused | None] = []
        self._outstanding = 0

    @property
    def busy(self) -> bool:
        return self._outstanding > 0

    def start(self, paths: list[Path]) -> None:
        if self.busy:
            raise RuntimeError("an import is already running")
        if not paths:
            self.finished.emit([])
            return
        self._results = [None] * len(paths)
        self._outstanding = len(paths)
        pool = QThreadPool.globalInstance()
        for index, path in enumerate(paths):
            pool.start(_Job(index, path, self._delivery))

    def _delivered(self, index: int, result: object) -> None:
        assert isinstance(result, (Prepared, Refused))
        self._results[index] = result
        self._outstanding -= 1
        if self._outstanding == 0:
            done = [each for each in self._results if each is not None]
            self._results = []
            self.finished.emit(done)
