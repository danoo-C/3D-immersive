"""The media pool: every imported sample, where it came from, and a way to drag it.

04, *Media pool*: a folder tree of imported audio, each row with its name,
duration and a one-line waveform, a filter above it, and rows that drag onto
the timeline. The folders mirror those beneath what was imported - the common
folder of everything in the pool is the root, so importing one folder of
samples shows its subfolders and not the path to it.

Rebuilt from the document whenever it changes. A pool holds tens or hundreds
of samples, not millions, and a rebuild cannot drift out of step with the
model the way an incremental update can.
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePath

from PySide6.QtCore import (
    QByteArray,
    QMimeData,
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

from immersive.core.document import Document
from immersive.core.media_store import MediaStore
from immersive.core.model import MediaFile
from immersive.core.time import SAMPLE_RATE
from immersive.ui import theme
from immersive.ui.widgets.placeholder import Panel
from immersive.ui.widgets.waveform import paint_peaks

#: What a dragged row carries: a JSON list of media ids. Named in 04 so the
#: timeline at M3 has a contract to accept rather than a guess.
MIME: str = "application/x-3dimmersive-media"

#: Where a row keeps the id of the sample it shows.
ID_ROLE = Qt.ItemDataRole.UserRole + 1

NAME, DURATION, WAVEFORM = range(3)

#: How wide a row's waveform is drawn. Enough to see a sample's shape - a hit
#: from a pad - in a column that also has to hold a name.
THUMBNAIL_WIDTH = 72

#: A missing sample's row says so in words as well as in `warn` (04,
#: *Accessibility and feel*: never by colour alone).
MISSING_MARK = "⚠ "


def duration(frames: int) -> str:
    """A length a pool row has room for: `1.40s` under a minute, `3:12` above.

    Compact because the column shares 250 px with a name and a waveform; the
    exact length belongs to the parameters pane, which has the room.
    """
    seconds = frames / SAMPLE_RATE
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}:{rest:02d}"


class _Model(QStandardItemModel):
    """The pool's rows, and what dragging them carries."""

    def mimeTypes(self) -> list[str]:
        return [MIME]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:  # type: ignore[override]
        ids: list[str] = []
        for index in indexes:
            media_id = index.data(ID_ROLE)
            if isinstance(media_id, str) and media_id not in ids:
                ids.append(media_id)
        data = QMimeData()
        data.setData(MIME, QByteArray(json.dumps(ids).encode("utf-8")))
        return data


class _Thumbnail(QStyledItemDelegate):
    """The waveform column, drawn by the waveform widget's own drawing."""

    def __init__(self, pool: MediaPool) -> None:
        super().__init__(pool)
        self._pool = pool

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        media_id = index.data(ID_ROLE)
        if not isinstance(media_id, str):
            return
        media = self._pool.media(media_id)
        if media is None:
            return
        area = option.rect.adjusted(2, 3, -2, -3)
        paint_peaks(
            painter, area, self._pool.store.peaks(media_id), missing=media.missing
        )

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(THUMBNAIL_WIDTH, 22)


class MediaPool(Panel):
    """04's media pool, over a document and the session's store."""

    def __init__(
        self, document: Document, store: MediaStore, parent: QWidget | None = None
    ) -> None:
        super().__init__("Media Pool", parent)
        self._document = document
        self.store = store

        self.filter = QLineEdit()
        self.filter.setObjectName("PoolFilter")
        self.filter.setPlaceholderText("Filter")
        self.filter.setClearButtonEnabled(True)

        self.model = _Model(0, 3, self)
        # No title over the waveform: the column says what it is.
        self.model.setHorizontalHeaderLabels(["Name", "Length", ""])
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(NAME)
        self.filter.textChanged.connect(self._filtered)

        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setItemDelegateForColumn(WAVEFORM, _Thumbnail(self))
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(12)
        # The column is narrow - 250 px by default - so the name takes what
        # is left after the other two, rather than three fixed widths that
        # squeezed the thumbnail to a smear and scrolled sideways.
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(DURATION, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WAVEFORM, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(WAVEFORM, THUMBNAIL_WIDTH)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.body().addWidget(self.filter)
        self.body().addWidget(self.tree, 1)

        document.observe(self.rebuild)
        self.rebuild()
        self.retheme()

    # ---------------------------------------------------------------- reading

    def media(self, media_id: str) -> MediaFile | None:
        for media in self._document.project.media_pool:
            if media.id == media_id:
                return media
        return None

    # --------------------------------------------------------------- building

    def rebuild(self) -> None:
        """Every row again, from the document as it is now."""
        self.model.removeRows(0, self.model.rowCount())
        pool = self._document.project.media_pool
        root = _common_folder([Path(media.path).parent for media in pool])
        folders: dict[tuple[str, ...], QStandardItem] = {}
        for media in pool:
            parent = self._folder(folders, _parts(Path(media.path).parent, root))
            parent.appendRow(self._row(media))
        self.tree.expandAll()

    def _folder(
        self, folders: dict[tuple[str, ...], QStandardItem], parts: tuple[str, ...]
    ) -> QStandardItem:
        """The item for the folder at `parts`, making it and its parents."""
        if not parts:
            invisible = self.model.invisibleRootItem()
            assert invisible is not None
            return invisible
        if parts not in folders:
            above = self._folder(folders, parts[:-1])
            item = QStandardItem(parts[-1])
            item.setEditable(False)
            item.setDragEnabled(False)
            item.setToolTip(str(PurePath(*parts)))
            spacers = [QStandardItem() for _ in range(2)]
            for spacer in spacers:
                spacer.setEditable(False)
                spacer.setDragEnabled(False)
            above.appendRow([item, *spacers])
            folders[parts] = item
        return folders[parts]

    def _row(self, media: MediaFile) -> list[QStandardItem]:
        name = QStandardItem((MISSING_MARK if media.missing else "") + media.name)
        name.setToolTip(media.path)
        if media.missing:
            name.setForeground(QBrush(QColor(theme.color("warn"))))
        length = QStandardItem(duration(media.frames))
        length.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        wave = QStandardItem()
        row = [name, length, wave]
        for item in row:
            item.setEditable(False)
            item.setData(media.id, ID_ROLE)
        return row

    # ---------------------------------------------------------------- filter

    def _filtered(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        self.tree.expandAll()

    # ----------------------------------------------------------------- theme

    def retheme(self) -> None:
        """The panel's header, and the rows' `warn`, which the items bake in."""
        super().retheme()
        if hasattr(self, "model"):
            self.rebuild()


def _common_folder(folders: list[Path]) -> Path | None:
    """The deepest folder every sample lives beneath, or `None` for none.

    Samples on two Windows drives have no common folder at all; each then
    shows under its full path.
    """
    if not folders:
        return None
    try:
        return Path(os.path.commonpath([str(folder) for folder in folders]))
    except ValueError:
        return None


def _parts(folder: Path, root: Path | None) -> tuple[str, ...]:
    if root is None:
        return PurePath(folder).parts
    return folder.relative_to(root).parts
