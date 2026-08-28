"""User-facing notifications. Every QML-facing mutation is an `@intent`: if it raises, the
message lands in the status bar instead of vanishing into a swallowed slot exception."""
from __future__ import annotations

import functools
import sys
import time

from PySide6.QtCore import Property, QObject, Signal, Slot


class Notifier(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_error = ""
        self._status = "ready"
        self._history: list[dict] = []

    @Property(str, notify=changed)
    def lastError(self) -> str:
        return self._last_error

    @Property(str, notify=changed)
    def status(self) -> str:
        return self._status

    def error(self, text: str):
        self._last_error = text
        self._history.append({"level": "error", "text": text, "ts": time.time()})
        print(f"[error] {text}", file=sys.stderr, flush=True)
        self.changed.emit()

    def info(self, text: str):
        self._status = text
        self._history.append({"level": "info", "text": text, "ts": time.time()})
        self.changed.emit()

    @Slot()
    def dismiss(self):
        self._last_error = ""
        self.changed.emit()

    def history(self) -> list[dict]:
        return list(self._history)


def intent(fn):
    """Report exceptions from a QML-facing slot to `self.notifier` (if any), then re-raise so
    Python callers (IPC, tests) still see them.

    Hot-reload note: the reloader swaps *code* into the old wrapper object and copies function
    attributes (`__wrapped__`) from the new one, so the wrapper must find the current body via
    the attribute, not via its closure."""
    name = fn.__name__

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        body = getattr(type(self), name).__wrapped__
        try:
            return body(self, *args, **kwargs)
        except Exception as e:
            notifier = getattr(self, "notifier", None)
            if notifier is not None:
                notifier.error(f"{name}: {e}")
            raise
    return wrapper
