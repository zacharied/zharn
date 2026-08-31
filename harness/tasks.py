"""Minimal task store: the unit every context belongs to. Schema mirrors bb's Tasks plugin
(docs/DESIGN.md §3b); the full store (labels, comments, attachments) is roadmap step 3."""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness.notify import intent
from harness.qmodels import DictListModel

STATUSES = ["backlog", "todo", "in_progress", "in_review", "done", "canceled"]
PRIORITIES = ["urgent", "high", "medium", "low", "none"]
ROLES = ["key", "title", "status", "priority", "description", "contextCount", "workingCount", "createdAt"]

DEMO = [
    {"title": "Hot reload for QML + Python", "status": "in_review", "priority": "high",
     "description": "Generation model for QML, in-place code swap for Python. See docs/DESIGN.md."},
    {"title": "JetBrains-style docking", "status": "in_progress", "priority": "high",
     "description": "Strips, docks, splittable tab groups, tab drag & drop."},
    {"title": "Terminal panel (pyte)", "status": "todo", "priority": "medium", "description": "A QML terminal on top of pyte."},
    {"title": "Git status panel", "status": "todo", "priority": "low", "description": ""},
    {"title": "Task store: labels, comments, attachments", "status": "backlog", "priority": "medium", "description": ""},
]


class TaskStore(QObject):
    tasksChanged = Signal()
    notifier = None

    def __init__(self, data_dir: Path, contexts, prefix: str = "ABC", parent=None):
        super().__init__(parent)
        self._path = data_dir / "tasks.json"
        self._contexts = contexts
        self._prefix = prefix
        self._tasks: list[dict] = []
        self._next = 1
        self._model = DictListModel(ROLES, self)
        self._load()
        contexts.contextsChanged.connect(self._refresh)

    @Property(QObject, constant=True)
    def model(self): return self._model

    @Property("QVariantList", constant=True)
    def statuses(self): return STATUSES

    def _load(self):
        try:
            data = json.loads(self._path.read_text())
            self._tasks, self._next = data["tasks"], data["next"]
        except (OSError, ValueError, KeyError):
            for d in DEMO:
                self._tasks.append({**d, "key": f"{self._prefix}-{self._next}", "createdAt": time.time()})
                self._next += 1
            self._persist()
        self._refresh()

    def _persist(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"tasks": self._tasks, "next": self._next}, indent=1))

    def _row(self, t: dict) -> dict:
        ctxs = self._contexts.contexts_for(t["key"])
        return {**t, "contextCount": len(ctxs), "workingCount": sum(1 for x in ctxs if x.status in ("starting", "working"))}

    def _refresh(self):
        self._model.reset([self._row(t) for t in self._tasks])
        self.tasksChanged.emit()

    def _find(self, key: str) -> dict | None:
        return next((t for t in self._tasks if t["key"].lower() == (key or "").lower()), None)

    @Slot(str, result="QVariantMap")
    def get(self, key):
        t = self._find(key)
        return self._row(t) if t else {}

    @Slot(result="QVariantList")
    def list(self):
        return [self._row(t) for t in self._tasks]

    @Slot(str, str, result=str)
    @intent
    def create(self, title, description=""):
        t = {"key": f"{self._prefix}-{self._next}", "title": title, "status": "todo", "priority": "medium",
             "description": description, "createdAt": time.time()}
        self._next += 1
        self._tasks.append(t)
        self._persist()
        self._refresh()
        return t["key"]

    @Slot(str, str)
    @intent
    def setStatus(self, key, status):
        t = self._find(key)
        if t and status in STATUSES:
            t["status"] = status
            self._persist()
            self._refresh()

    @Slot(str, str, str, result=str)
    @intent
    def dispatch(self, key, role_name, prompt) -> str:
        """bb-style: task context + report-back contract + the user's prompt → new context."""
        t = self._find(key)
        if t is None:
            raise ValueError(f"unknown task {key!r}")
        full = (f"# Task {t['key']}: {t['title']}\n\n{t.get('description', '')}\n\n"
                f"## Report-back contract\nYou are working on task {t['key']} inside zharn. "
                f"Spawn helpers with `$HARNESS_CLI context new --role <name> --prompt \"...\"` "
                f"and wait with `$HARNESS_CLI context wait <id>`. Keep the task's status accurate.\n\n## Instructions\n{prompt}")
        title = prompt.strip().splitlines()[0][:60] if prompt.strip() else role_name
        cid = self._contexts.spawn(role_name, full, story_key=key, owner="human", title=title)
        if t["status"] in ("backlog", "todo"):
            t["status"] = "in_progress"
            self._persist()
        self._refresh()
        return cid

    @Slot(str, result="QVariantList")
    def contextsFor(self, key):
        return [x.summary() for x in self._contexts.contexts_for(key)]
