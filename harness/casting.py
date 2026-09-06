"""Casting: the three picks a character is spawned with — a model, an effort, and a preset that says
which skills it wakes up with — resolved against the position it was cast into (lifecycle spec §1, §5).

A preset controls skills and nothing else. Everything a role used to bundle besides model and effort —
instructions, the outline-first rule, the permission ceiling — belongs to the position, which nobody picks:
Start casts a protagonist, `call` casts a friend, New Context opens a bare one. The provider is read off
the model."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness.notify import intent

PRESET_FIELDS = ("name", "skills")
CAST_FIELDS = ("position", "label", "instructions", "outline_first", "permission", "provider",
               "model", "effort", "preset")
WHOLE_TREE = "*"


class CastStore(QObject):
    presetsChanged = Signal()
    notifier = None

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._path = Path(data_dir) / "presets.json"
        self._user: list[dict] = []
        try:
            self._user = json.loads(self._path.read_text())
        except (OSError, ValueError):
            pass

    # ---- what the selectors offer

    @Property("QVariantList", constant=True)
    def models(self):
        return [{"id": m.get("id", ""), "label": m.get("label") or m.get("id", ""),
                 "provider": m.get("provider", "claude-code")} for m in getattr(cfg, "MODELS", [])]

    @Property("QVariantList", constant=True)
    def efforts(self):
        return list(getattr(cfg, "EFFORTS", [""]))

    @Property("QVariantList", constant=True)
    def positions(self):
        return list(getattr(cfg, "CAST_POSITIONS", {}))

    @Slot(result="QVariantList")
    def modelIds(self):
        return [m["id"] for m in self.models]

    @Slot(result="QVariantList")
    def modelLabels(self):
        return [m["label"] for m in self.models]

    @Slot(str, result=str)
    def providerOf(self, model_id):
        for m in self.models:
            if m["id"] == (model_id or ""):
                return m["provider"]
        return "claude-code"

    # ---- presets: skills, and nothing else

    def _presets(self) -> list[dict]:
        out, seen = [], set()
        for p in list(getattr(cfg, "DEFAULT_PRESETS", [])) + self._user:
            full = {"name": p.get("name", ""), "skills": list(p.get("skills", []))}
            if full["name"].lower() in seen:
                out = [x if x["name"].lower() != full["name"].lower() else full for x in out]
                continue
            seen.add(full["name"].lower())
            out.append(full)
        return out

    @Property("QVariantList", notify=presetsChanged)
    def presets(self):
        return self._presets()

    @Slot(result="QVariantList")
    def presetNames(self):
        return [p["name"] for p in self._presets()]

    @Slot(str, result="QVariantMap")
    def preset(self, name):
        for p in self._presets():
            if p["name"].lower() == (name or "").lower():
                return p
        return {}

    def preset_skills(self, name) -> list[str] | None:
        """The skill directories the preset exposes; None for the whole tree (["*"], or unknown)."""
        p = self.preset(name)
        if not p or WHOLE_TREE in p["skills"]:
            return None
        return list(p["skills"])

    @Slot("QVariantMap")
    @intent
    def save(self, preset):
        preset = {"name": preset.get("name", ""), "skills": list(preset.get("skills", []))}
        self._user = [p for p in self._user if p["name"].lower() != preset["name"].lower()] + [preset]
        self._persist()

    @Slot(str)
    @intent
    def remove(self, name):
        self._user = [p for p in self._user if p["name"].lower() != (name or "").lower()]
        self._persist()

    def _persist(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._user, indent=1))
        self.presetsChanged.emit()

    # ---- the cast a context is spawned from

    @Slot(str, str, str, str, result="QVariantMap")
    def rebuild(self, position, model="", effort="", preset="") -> dict:
        """The cast of a character that already exists, from the picks it carries. A pick that has stopped
        resolving — a preset the author deleted, an effort a fork of the config no longer offers — falls back
        to the position's own. A preset governs skills and nothing else: raising here would let a deleted one
        take the position's instructions and its outline rule down with it."""
        if not getattr(cfg, "CAST_POSITIONS", {}).get(position or ""):
            return {}
        if effort and effort not in getattr(cfg, "EFFORT_FLAGS", {}):
            effort = ""
        if preset and not self.preset(preset):
            preset = ""
        return self.resolve(position, model, effort, preset)

    @Slot(str, str, str, str, result="QVariantMap")
    def resolve(self, position, model="", effort="", preset="") -> dict:
        pos = getattr(cfg, "CAST_POSITIONS", {}).get(position or "")
        if not pos:
            raise ValueError(f"unknown position {position!r}")
        effort = effort or pos.get("effort", "")
        if effort and effort not in getattr(cfg, "EFFORT_FLAGS", {}):
            raise ValueError(f"unknown effort {effort!r}")
        preset = preset or pos.get("preset", "") or getattr(cfg, "DEFAULT_PRESET", "full")
        if not self.preset(preset):
            raise ValueError(f"unknown preset {preset!r}")
        model = model if model else pos.get("model", "")
        return {"position": position, "label": pos.get("label", position),
                "instructions": pos.get("instructions", ""), "outline_first": bool(pos.get("outline_first")),
                "permission": pos.get("permission", "auto"), "provider": self.providerOf(model),
                "model": model, "effort": effort, "preset": self.preset(preset)["name"]}
