"""Generic list model over dict rows, for QML ListViews/Repeaters."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Slot


class DictListModel(QAbstractListModel):
    countChanged = Signal()

    def __init__(self, roles: list[str], parent=None):
        super().__init__(parent)
        self._roles = list(roles)
        self._ids = {Qt.ItemDataRole.UserRole + i: r for i, r in enumerate(self._roles)}
        self._rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self):
        return {k: QByteArray(v.encode()) for k, v in self._ids.items()}

    def data(self, index, role):
        if not index.isValid():
            return None
        return self._rows[index.row()].get(self._ids.get(role, ""))

    def rows(self):
        return self._rows

    def reset(self, rows: list[dict]):
        self.beginResetModel()
        self._rows = [dict(r) for r in rows]
        self.endResetModel()
        self.countChanged.emit()

    def upsert(self, row: dict, key: str = "id"):
        for i, r in enumerate(self._rows):
            if r.get(key) == row.get(key):
                self._rows[i] = {**r, **row}
                self.dataChanged.emit(self.index(i), self.index(i))
                return
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(dict(row))
        self.endInsertRows()
        self.countChanged.emit()

    def remove(self, value, key: str = "id"):
        for i, r in enumerate(self._rows):
            if r.get(key) == value:
                self.beginRemoveRows(QModelIndex(), i, i)
                self._rows.pop(i)
                self.endRemoveRows()
                self.countChanged.emit()
                return

    @Slot(result=int)
    def count(self):
        return len(self._rows)

    @Slot(int, result="QVariantMap")
    def get(self, i):
        return dict(self._rows[i]) if 0 <= i < len(self._rows) else {}
