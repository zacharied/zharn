"""WorkspaceStore: the QML face of a `harness.workspace.Workspace` (DESIGN §2; spec §2 identity, §3 repos).
Identity reads through; `repos()` carries §3.3 status; the intents are the author's repo actions from the
workspace page — register (path or URL, as `zharn repo add`), unregister (never deletes files), relocate."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from harness.environments import register_repo
from harness.lifecycle import Rejected
from harness.notify import intent


class WorkspaceStore(QObject):
    workspaceChanged = Signal()
    notifier = None

    def __init__(self, workspace, stories, parent=None):
        super().__init__(parent)
        self._ws = workspace
        self._stories = stories

    # ---------------------------------------------------------------- identity (§2.1)
    @Property(str, notify=workspaceChanged)
    def name(self) -> str:
        return self._ws.name

    @Property(str, notify=workspaceChanged)
    def prefix(self) -> str:
        return self._ws.prefix

    @Property(str, constant=True)
    def dir(self) -> str:
        return str(self._ws.dir)

    @Property(str, constant=True)
    def id(self) -> str:
        return self._ws.id

    # ---------------------------------------------------------------- repos (§3)
    @Slot(result="QVariantList")
    def repos(self) -> list[dict]:
        return self._stories.repo_list()

    def _changed(self):
        """Every successful mutation: the workspace signal, then story rows re-derive (env rows carry repo data)."""
        self.workspaceChanged.emit()
        self._stories._refresh()

    def _require(self, name: str) -> dict:
        r = self._ws.repo(name)
        if r is None:
            raise Rejected(f"no repo named {name!r}")
        return r

    @Slot(str, str, str, str, str, result="QVariantMap")
    @intent
    def register(self, spec, name="", checks="", setup="", base="") -> dict:
        rec = register_repo(self._ws, spec, name=name, checks=checks, setup=setup, base=base)
        self._changed()
        return rec

    @Slot(str)
    @intent
    def unregister(self, name):
        self._require(name)
        self._ws.unregister(name)
        self._changed()

    @Slot(str, str, result="QVariantMap")
    @intent
    def relocate(self, name, path) -> dict:
        self._require(name)
        p = Path(path).resolve()
        if not (p / ".git").exists():
            raise ValueError(f"{p} is not a git repository")
        rec = self._ws.relocate(name, p)
        self._changed()
        return rec
