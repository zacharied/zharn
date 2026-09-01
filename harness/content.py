"""Content registry: what can live in a Main Content Container or a dock panel.

Adding a kind = one entry here + one QML file in qml/content/. This module is hot-reloaded,
so the registry object always reads the module-level dict at call time.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Slot

KINDS: dict[str, dict] = {
    # icon = a name under qml/icons/ (see harness/icons.py)
    "board":    {"title": "Stories",  "qml": "content/StoryBoard.qml", "panel": True,  "icon": "stories"},
    "cast":     {"title": "Cast",     "qml": "content/Cast.qml",       "panel": True,  "icon": "cast"},
    "contexts": {"title": "Contexts", "qml": "content/Contexts.qml",   "panel": True,  "icon": "contexts"},
    "files":    {"title": "Files",    "qml": "content/Files.qml",      "panel": True,  "icon": "files"},
    "git":      {"title": "Git",      "qml": "content/Git.qml",        "panel": True,  "icon": "git"},
    "terminal": {"title": "Terminal", "qml": "content/Terminal.qml",   "panel": True,  "icon": "terminal"},
    "welcome":  {"title": "Welcome",  "qml": "content/Welcome.qml",    "panel": False, "icon": "home"},
    "story":    {"title": "Story",    "qml": "content/Story.qml",      "panel": False, "icon": "story"},
    "context":  {"title": "Context",  "qml": "content/Context.qml",    "panel": False, "icon": "context"},
    "document": {"title": "Document", "qml": "content/Document.qml",   "panel": False, "icon": "files"},
}


class ContentRegistry(QObject):
    """Thin QObject facade over KINDS so QML can ask 'what renders this kind?'."""

    def __init__(self, qml_dir):
        super().__init__()
        self._qml_dir = qml_dir

    def _entry(self, kind: str) -> dict:
        return KINDS.get(kind) or {"title": kind, "qml": "content/Missing.qml", "panel": False, "icon": "error"}

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
