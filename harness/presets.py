"""Delegation presets: the execution config a thread is spawned with (bb Tasks parity)."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg

FIELDS = ("name", "provider", "model", "reasoning", "permission", "environment", "instructions")


class PresetStore(QObject):
    presetsChanged = Signal()

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._path = data_dir / "presets.json"
        self._user: list[dict] = []
        try:
            self._user = json.loads(self._path.read_text())
        except (OSError, ValueError):
            pass

    def _all(self) -> list[dict]:
        out, seen = [], set()
        for p in list(getattr(cfg, "DEFAULT_PRESETS", [])) + self._user:
            full = {"provider": "claude-code", "model": "", "reasoning": "medium", "permission": "auto",
                    "environment": "project-default", "instructions": "", **p}
            if full["name"] in seen:
                out = [x for x in out if x["name"] != full["name"]]  # user overrides default
            seen.add(full["name"])
            out.append(full)
        return out

    @Property("QVariantList", notify=presetsChanged)
    def presets(self):
        return self._all()

    @Slot(result="QVariantList")
    def names(self):
        return [p["name"] for p in self._all()]

    @Slot(str, result="QVariantMap")
    def get(self, name):
        for p in self._all():
            if p["name"].lower() == (name or "").lower():
                return p
        return {}

    @Slot("QVariantMap")
    def save(self, preset):
        preset = {k: preset.get(k, "") for k in FIELDS}
        self._user = [p for p in self._user if p["name"].lower() != preset["name"].lower()] + [preset]
        self._persist()

    @Slot(str)
    def remove(self, name):
        self._user = [p for p in self._user if p["name"].lower() != name.lower()]
        self._persist()

    def _persist(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._user, indent=1))
        self.presetsChanged.emit()
