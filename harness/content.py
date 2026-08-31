"""Content registry: what can live in a Main Content Container or a dock panel.

Adding a kind = one entry here + one QML file in qml/content/. This module is hot-reloaded,
so the registry object always reads the module-level dict at call time.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Slot

KINDS: dict[str, dict] = {
    # dockable panels (can also be opened as a tab in an MCC)
    "tasks":        {"title": "Tasks",        "qml": "content/TaskBoard.qml",   "panel": True,  "icon": "☰"},
    "task_details": {"title": "Task Details", "qml": "content/TaskDetails.qml", "panel": True,  "icon": "i"},
    "files":        {"title": "Files",        "qml": "content/Files.qml",       "panel": True,  "icon": "▤"},
    "git":          {"title": "Git",          "qml": "content/Git.qml",         "panel": True,  "icon": "⎇"},
    "terminal":     {"title": "Terminal",     "qml": "content/Terminal.qml",    "panel": True,  "icon": ">_"},
    "contexts":     {"title": "Contexts",     "qml": "content/Contexts.qml",    "panel": True,  "icon": "≡"},
    # documents / conversations (MCC only)
    "welcome":      {"title": "Welcome",      "qml": "content/Welcome.qml",     "panel": False, "icon": "★"},
    "context":      {"title": "Context",      "qml": "content/Context.qml",     "panel": False, "icon": "💬"},
    "task":         {"title": "Task",         "qml": "content/TaskView.qml",    "panel": False, "icon": "☐"},
    "document":     {"title": "Document",     "qml": "content/Document.qml",    "panel": False, "icon": "▢"},
}


class ContentRegistry(QObject):
    """Thin QObject facade over KINDS so QML can ask 'what renders this kind?'."""

    def __init__(self, qml_dir):
        super().__init__()
        self._qml_dir = qml_dir

    def _entry(self, kind: str) -> dict:
        return KINDS.get(kind) or {"title": kind, "qml": "content/Missing.qml", "panel": False, "icon": "?"}

    @Slot(str, result=str)
    def qmlFor(self, kind: str) -> str:
        return (self._qml_dir / self._entry(kind)["qml"]).as_uri()

    @Slot(str, result=str)
    def titleFor(self, kind: str) -> str:
        return self._entry(kind)["title"]

    @Slot(str, result=str)
    def iconFor(self, kind: str) -> str:
        return self._entry(kind)["icon"]

    @Slot(result="QVariantList")
    def panelKinds(self):
        return [k for k, v in KINDS.items() if v["panel"]]
