"""Long-lived state exposed to QML. Instances outlive every QML generation and every Python
reload (the reloader swaps method code into these classes in place)."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from harness import layout as layout_mod
from harness.notify import Notifier, intent


class Session:
    """Persisted app state: layout tree + window geometry. Survives restarts."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {}
        try:
            self.data = json.loads(path.read_text())
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=1))
        except OSError:
            pass


class LayoutStore(QObject):
    layoutChanged = Signal()
    notifier = None

    def __init__(self, session: Session):
        super().__init__()
        self._session = session
        saved = session.data.get("layout")
        self._layout = layout_mod.Layout(saved) if saved else layout_mod.Layout()

    def _commit(self):
        self._session.data["layout"] = self._layout.data
        self._session.save()
        self.layoutChanged.emit()

    @Property(str, notify=layoutChanged)
    def layoutJson(self) -> str:
        return self._layout.to_json()

    @Property(str, notify=layoutChanged)
    def activeGroup(self) -> str:
        return self._layout.active_group()["id"]

    # -- intents (QML → Python). Names mirror harness.layout.Layout.
    @Slot(str, str, str)
    @Slot(str, str, str, str)
    @intent
    def openContent(self, kind, key, title, group_id=""):
        self._layout.open(kind, key or None, title or None, group_id or None)
        self._commit()

    @Slot(str, int)
    @intent
    def activateTab(self, group_id, index):
        self._layout.activate(group_id, index)
        self._commit()

    @Slot(str, int)
    @intent
    def closeTab(self, group_id, index):
        self._layout.close(group_id, index)
        self._commit()

    @Slot(str, str)
    @intent
    def splitGroup(self, group_id, orientation):
        g = self._layout.find(group_id)[0]
        active = g["tabs"][g["active"]] if g["tabs"] else None
        self._layout.split_group(group_id, orientation, dict(active) if active else None)
        self._commit()

    @Slot(str, int, str, int)
    @intent
    def moveTab(self, from_group, index, to_group, to_index):
        self._layout.move(from_group, index, to_group, None if to_index < 0 else to_index)
        self._commit()

    @Slot(str, int, str, str)
    @intent
    def moveTabToEdge(self, from_group, index, target_group, edge):
        self._layout.move_to_edge(from_group, index, target_group, edge)
        self._commit()

    @Slot(str, "QVariantList")
    @intent
    def setRatios(self, split_id, ratios):
        self._layout.set_ratios(split_id, [float(r) for r in ratios])
        self._commit()

    @Slot(str, str)
    @intent
    def togglePanel(self, side, panel):
        self._layout.toggle_panel(side, panel)
        self._commit()

    @Slot(str)
    @intent
    def showPanel(self, panel):
        self._layout.show_panel(panel)
        self._commit()

    @Slot(str, str)
    @intent
    def setDockMode(self, side, mode):
        self._layout.set_dock_mode(side, mode)
        self._commit()

    @Slot(str, int)
    @intent
    def setDockSize(self, side, size):
        self._layout.set_dock_size(side, size)
        self._commit()

    @Slot(str, str)
    @intent
    def movePanel(self, panel, to_side):
        self._layout.move_panel(panel, to_side)
        self._commit()

    @Slot()
    @intent
    def resetLayout(self):
        self._layout = layout_mod.Layout()
        self._commit()


class AppStore(QObject):
    """Root object QML sees as `app`."""
    themeChanged = Signal()
    hotChanged = Signal()

    def __init__(self, session: Session, layout_store: LayoutStore, content, theme: dict,
                 contexts=None, roles=None, stories=None, workspace=None, notifier=None):
        super().__init__()
        self._session = session
        self._layout = layout_store
        self._content = content
        self._contexts, self._roles = contexts, roles
        self._stories, self._workspace = stories, workspace
        self._notify = notifier or Notifier()
        self._notify.setParent(self)
        self._ipc_path = ""
        self._theme = dict(theme)
        self._generation = 0
        self._reload_error = ""
        self._restart_required = False
        self._watch_mode = "-"

    @Property(QObject, constant=True)
    def layout(self):
        return self._layout

    @Property(QObject, constant=True)
    def content(self):
        return self._content

    @Property(QObject, constant=True)
    def contexts(self):
        return self._contexts

    @Property(QObject, constant=True)
    def roles(self):
        return self._roles

    @Property(QObject, constant=True)
    def stories(self):
        return self._stories

    @Property(str, constant=True)
    def workspaceDir(self):
        return str(self._workspace.dir) if self._workspace else ""

    @Property(QObject, constant=True)
    def notify(self):
        return self._notify

    @Property(str, constant=True)
    def ipcPath(self):
        return self._ipc_path

    @Property("QVariantMap", notify=themeChanged)
    def theme(self):
        return self._theme

    def set_theme(self, theme: dict):
        self._theme = dict(theme)
        self.themeChanged.emit()

    # -- hot-reload telemetry (shown in the status bar)
    @Property(int, notify=hotChanged)
    def generation(self):
        return self._generation

    @Property(str, notify=hotChanged)
    def reloadError(self):
        return self._reload_error

    @Property(bool, notify=hotChanged)
    def restartRequired(self):
        return self._restart_required

    @Property(str, notify=hotChanged)
    def watchMode(self):
        return self._watch_mode

    def set_hot(self, generation=None, error=None, restart_required=None, watch_mode=None):
        if generation is not None:
            self._generation = generation
        if error is not None:
            self._reload_error = error
        if restart_required is not None:
            self._restart_required = restart_required
        if watch_mode is not None:
            self._watch_mode = watch_mode
        self.hotChanged.emit()

    # -- window geometry persistence
    @Slot(int, int, int, int)
    def saveGeometry(self, x, y, w, h):
        self._session.data["window"] = {"x": x, "y": y, "w": w, "h": h}
        self._session.save()

    @Property("QVariantMap", constant=True)
    def savedGeometry(self):
        return self._session.data.get("window") or {"x": -1, "y": -1, "w": 1400, "h": 900}

    requestRestart = Signal()

    @Slot()
    def restart(self):
        self.requestRestart.emit()
