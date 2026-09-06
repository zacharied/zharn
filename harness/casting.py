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

    @Property(str, constant=True)
    def defaultPosition(self):
        """What Start casts. The selectors seed from this position's own picks, so no view has to
        name a position of its own to know what it is about to do."""
        return getattr(cfg, "DEFAULT_POSITION", "protagonist")

    @Property(str, constant=True)
    def barePosition(self):
        """What New Context opens."""
        return getattr(cfg, "DEFAULT_BARE_POSITION", "bare")

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

    @Slot(str, result="QVariantMap")
    def defaultsFor(self, position) -> dict:
        """The three picks a position starts on: what the selectors seed from, so a row that nobody
        touched reads as what pressing the button will actually do. Empty for an unknown position."""
        pos = getattr(cfg, "CAST_POSITIONS", {}).get(position or "")
        if not pos:
            return {}
        return {"model": pos.get("model", ""), "effort": pos.get("effort", ""),
                "preset": pos.get("preset", "") or getattr(cfg, "DEFAULT_PRESET", "full")}

    @Slot(str, str, str, str, result="QVariantMap")
    def rebuild(self, position, model=None, effort=None, preset=None) -> dict:
        """The cast of a character that already exists, from the picks it carries. A pick that has stopped
        resolving — a preset the author deleted, an effort a fork of the config no longer offers — falls back
        to the position's own. A preset governs skills and nothing else: raising here would let a deleted one
        take the position's instructions and its outline rule down with it. An empty effort is not a pick that
        stopped resolving: config.EFFORTS offers it, and it survives."""
        if not getattr(cfg, "CAST_POSITIONS", {}).get(position or ""):
            return {}
        if effort and effort not in getattr(cfg, "EFFORT_FLAGS", {}):
            effort = None
        if preset and not self.preset(preset):
            preset = None
        return self.resolve(position, model, effort, preset)

    @Slot(str, str, str, str, result="QVariantMap")
    def resolve(self, position, model=None, effort=None, preset=None) -> dict:
        """A position plus three picks. None is "nobody picked" and takes the position's own; a string is
        the pick, empty included — config.MODELS ships an "" id for the CLI's own default and config.EFFORTS
        an "" for the provider's own, and neither may be swallowed by the position's. A preset is the one
        exception: the preset list has no empty member, so "" there also reads as the position's."""
        pos = getattr(cfg, "CAST_POSITIONS", {}).get(position or "")
        if not pos:
            raise ValueError(f"unknown position {position!r}")
        effort = pos.get("effort", "") if effort is None else effort
        if effort and effort not in getattr(cfg, "EFFORT_FLAGS", {}):
            raise ValueError(f"unknown effort {effort!r}")
        preset = preset or pos.get("preset", "") or getattr(cfg, "DEFAULT_PRESET", "full")
        if not self.preset(preset):
            raise ValueError(f"unknown preset {preset!r}")
        model = pos.get("model", "") if model is None else model
        return {"position": position, "label": pos.get("label", position),
                "instructions": pos.get("instructions", ""), "outline_first": bool(pos.get("outline_first")),
                "permission": pos.get("permission", "auto"), "provider": self.providerOf(model),
                "model": model, "effort": effort, "preset": self.preset(preset)["name"]}
