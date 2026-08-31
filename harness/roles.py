"""Roles: what a character is cast from — provider, model, permission ceiling, instructions,
and whether it must get an outline approved before implementing (lifecycle spec §1, §7)."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness.notify import intent

FIELDS = ("name", "provider", "model", "reasoning", "permission", "environment", "instructions", "outline_first")
DEFAULTS = {"provider": "claude-code", "model": "", "reasoning": "medium", "permission": "auto",
            "environment": "project-default", "instructions": "", "outline_first": False}


class RoleStore(QObject):
    rolesChanged = Signal()
    notifier = None

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._path = data_dir / "roles.json"
        self._user: list[dict] = []
        try:
            self._user = json.loads(self._path.read_text())
        except (OSError, ValueError):
            pass

    def _all(self) -> list[dict]:
        out, seen = [], set()
        for r in list(getattr(cfg, "DEFAULT_ROLES", [])) + self._user:
            full = {**DEFAULTS, **r}
            if full["name"] in seen:
                out = [x if x["name"] != full["name"] else full for x in out]  # user overrides default, in place
                continue
            seen.add(full["name"])
            out.append(full)
        return out

    @Property("QVariantList", notify=rolesChanged)
    def roles(self):
        return self._all()

    @Slot(result="QVariantList")
    def names(self):
        return [r["name"] for r in self._all()]

    @Slot(str, result="QVariantMap")
    def get(self, name):
        for r in self._all():
            if r["name"].lower() == (name or "").lower():
                return r
        return {}

    @Slot("QVariantMap")
    @intent
    def save(self, role):
        role = {k: role[k] for k in FIELDS if k in role}
        self._user = [r for r in self._user if r["name"].lower() != role["name"].lower()] + [role]
        self._persist()

    @Slot(str)
    @intent
    def remove(self, name):
        self._user = [r for r in self._user if r["name"].lower() != name.lower()]
        self._persist()

    def _persist(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._user, indent=1))
        self.rolesChanged.emit()
