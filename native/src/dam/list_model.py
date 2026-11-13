"""One list of a catalog page, updated row by row so a list view keeps its place."""

import copy

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class PageModel(QAbstractListModel):
    """Exposes each row to QML as `modelData`, the name a plain JavaScript array model uses.

    Replacing a list view's model rebuilds its rows and returns it to the top, so `sync` applies
    only the difference. Callers also edit rows in place. `snapshots` keeps private copies, so a
    later `sync` can see which rows those edits changed; it suits short lists whose rows hold
    state of their own. Without it, `sync(touched=True)` refreshes the rows on screen instead.
    """

    ROW = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None, snapshots=False):
        super().__init__(parent)
        self._rows, self._snapshots = [], snapshots

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self):
        return {self.ROW: b"modelData"}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        return self._rows[index.row()] if role == self.ROW and index.isValid() else None

    def _kept(self, rows):
        return copy.deepcopy(rows) if self._snapshots else rows

    def sync(self, rows, reset=False, touched=False):
        rows = list(rows)
        if reset:
            self.beginResetModel()
            self._rows = self._kept(rows)
            self.endResetModel()
            return
        old = self._rows
        limit = min(len(old), len(rows))
        start = 0
        while start < limit and (old[start] is rows[start] or old[start] == rows[start]):
            start += 1
        end = 0
        while end < limit - start and (old[-1 - end] is rows[-1 - end] or old[-1 - end] == rows[-1 - end]):
            end += 1
        shared = min(len(old) - start - end, len(rows) - start - end)
        split = start + shared
        if shared:
            old[start:split] = self._kept(rows[start:split])
            self.dataChanged.emit(self.index(start), self.index(split - 1), [self.ROW])
        if len(old) - end > split:
            self.beginRemoveRows(QModelIndex(), split, len(old) - end - 1)
            del old[split:len(old) - end]
            self.endRemoveRows()
        elif len(rows) - end > split:
            self.beginInsertRows(QModelIndex(), split, len(rows) - end - 1)
            old[split:split] = self._kept(rows[split:len(rows) - end])
            self.endInsertRows()
        if not self._snapshots:
            # Equal rows may still be new objects, and later in-place edits go to the new ones.
            self._rows = rows
            if touched and rows:
                self.dataChanged.emit(self.index(0), self.index(len(rows) - 1), [self.ROW])
