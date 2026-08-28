"""Threads: one agent conversation each, always attached to a task, optionally parented to
another thread (agents spawning agents on the same task). Transcripts persist as JSONL."""
from __future__ import annotations

import json
import random
import string
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness.agents import ClaudeCodeProcess, StreamInterpreter, TranscriptModel
from harness.qmodels import DictListModel

THREAD_ROLES = ["id", "title", "taskKey", "status", "presetName", "parentId", "costUsd", "turns", "createdAt"]
SETTLED = ("idle", "failed", "stopped")


def new_thread_id() -> str:
    return "thr_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


class Thread(QObject):
    changed = Signal()

    def __init__(self, store: "ThreadStore", meta: dict):
        super().__init__(store)
        self._store = store
        self.meta = meta
        self._status = meta.get("status", "idle")
        self._last_error = ""
        self.transcript = TranscriptModel()
        self.transcript.setParent(self)
        self._interp = StreamInterpreter(self.transcript)
        self._interp.session_id = meta.get("sessionId", "")
        self._proc: ClaudeCodeProcess | None = None
        self._log_path = store.data_dir / "threads" / f"{meta['id']}.jsonl"

    # ---------------------------------------------------------------- QML-facing state
    @Property(str, constant=True)
    def id(self): return self.meta["id"]

    @Property(str, notify=changed)
    def title(self): return self.meta.get("title", "")

    @Property(str, constant=True)
    def taskKey(self): return self.meta.get("taskKey", "")

    @Property(str, constant=True)
    def presetName(self): return self.meta.get("preset", "")

    @Property(str, constant=True)
    def parentId(self): return self.meta.get("parentId", "")

    @Property(str, notify=changed)
    def status(self): return self._status

    @Property(str, notify=changed)
    def sessionId(self): return self._interp.session_id

    @Property(str, notify=changed)
    def model(self): return self._interp.model_name or self.meta.get("presetConfig", {}).get("model", "")

    @Property(float, notify=changed)
    def costUsd(self): return self._interp.cost_usd

    @Property(int, notify=changed)
    def turns(self): return self._interp.turns

    @Property(str, notify=changed)
    def lastError(self): return self._last_error

    @Property(QObject, constant=True)
    def transcriptModel(self): return self.transcript

    def last_assistant_text(self) -> str:
        for row in reversed(self.transcript.rows()):
            if row["role"] == "assistant" and row["kind"] == "text" and row["text"].strip():
                return row["text"]
        return ""

    def summary(self) -> dict:
        return {"id": self.id, "title": self.title, "taskKey": self.taskKey, "status": self._status,
                "presetName": self.presetName, "parentId": self.parentId, "costUsd": round(self._interp.cost_usd, 4),
                "turns": self._interp.turns, "createdAt": self.meta.get("createdAt", 0), "sessionId": self._interp.session_id,
                "model": self.model, "lastText": self.last_assistant_text()}

    # ---------------------------------------------------------------- lifecycle
    def _set_status(self, status: str):
        if status != self._status:
            self._status = status
            self.meta["status"] = status
            self._store._thread_changed(self)
            if status in SETTLED:
                self._store._thread_settled(self)
        self.changed.emit()

    def _log(self, record: dict):
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _env(self) -> dict:
        env = {"HARNESS_THREAD_ID": self.id, "HARNESS_TASK_KEY": self.taskKey, "HARNESS_ROOT": str(self._store.root),
               "HARNESS_CLI": f"{sys.executable} -m harness.cli"}
        env.update(self._store.extra_env())
        return env

    def _system_prompt(self) -> str:
        preset = self.meta.get("presetConfig", {})
        parts = [getattr(cfg, "AGENT_SYSTEM_PROMPT", "").format(thread_id=self.id, task_key=self.taskKey or "(none)")]
        if preset.get("instructions"):
            parts.append(preset["instructions"])
        return "\n\n".join(p for p in parts if p)

    def _spawn(self, resume: str = ""):
        preset = self.meta.get("presetConfig", {})
        extra = []
        effort = getattr(cfg, "EFFORT_FLAGS", {}).get(preset.get("reasoning", ""), [])
        extra += list(effort)
        self._proc = ClaudeCodeProcess(cwd=self.meta.get("cwd") or str(self._store.root), env=self._env(),
                                       model=preset.get("model", ""), permission=preset.get("permission", "auto"),
                                       resume=resume, system_prompt=self._system_prompt(), extra_args=extra)
        self._proc.event.connect(self._on_event)
        self._proc.stderrText.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.start()

    def start(self, prompt: str):
        self.send(prompt)

    @Slot(str)
    def send(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        self._log({"type": "harness.user", "text": text, "ts": time.time()})
        self.transcript.append(role="user", kind="text", text=text)
        self._last_error = ""
        if self._proc is None or not self._proc.running():
            self._set_status("starting")
            self._spawn(resume=self._interp.session_id)
        else:
            self._set_status("working")
        self._proc.send_user(text)

    @Slot()
    def stop(self):
        if self._proc and self._proc.running():
            self._proc.stop()
            self._set_status("stopped")

    def _on_event(self, ev: dict):
        self._log(ev)
        hint = self._interp.apply(ev)
        if hint:
            self._set_status(hint)
        else:
            self.changed.emit()

    def _on_stderr(self, text: str):
        if text.strip():
            self._last_error = text.strip()[-2000:]
            self.changed.emit()

    def _on_finished(self, code: int, status: str):
        self._proc = None
        if self._status in ("starting", "working"):
            self._last_error = self._last_error or f"process exited with code {code} ({status})"
            self.transcript.append(role="system", kind="error", text=self._last_error, isError=True)
            self._set_status("failed")

    def replay(self):
        """Rebuild the transcript from disk (no process)."""
        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") == "harness.user":
                self.transcript.append(role="user", kind="text", text=rec.get("text", ""))
            elif rec.get("type") == "harness.note":
                self.transcript.append(role="system", kind="note", text=rec.get("text", ""))
            else:
                self._interp.apply(rec)
        for row in self.transcript.rows():
            row["streaming"] = False
        if self._status in ("starting", "working"):
            self._status = "idle"

    def note(self, text: str):
        """A system note in the transcript (child lifecycle etc.)."""
        self._log({"type": "harness.note", "text": text, "ts": time.time()})
        self.transcript.append(role="system", kind="note", text=text)


class ThreadStore(QObject):
    threadsChanged = Signal()
    threadSettled = Signal(str)

    def __init__(self, root: Path, data_dir: Path, presets, parent=None):
        super().__init__(parent)
        self.root = root
        self.data_dir = data_dir
        self.presets = presets
        self.extra_env = lambda: {}
        self._threads: dict[str, Thread] = {}
        self._model = DictListModel(THREAD_ROLES, self)
        self._load()

    @Property(QObject, constant=True)
    def model(self): return self._model

    def _load(self):
        idx = self.data_dir / "threads" / "index.json"
        try:
            metas = json.loads(idx.read_text())
        except (OSError, ValueError):
            metas = []
        for meta in metas:
            t = Thread(self, meta)
            t.replay()
            self._threads[t.id] = t
        self._model.reset([t.summary() for t in self.all()])

    def _persist_index(self):
        idx = self.data_dir / "threads" / "index.json"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps([t.meta for t in self.all()], indent=1))

    def all(self) -> list[Thread]:
        return sorted(self._threads.values(), key=lambda t: t.meta.get("createdAt", 0))

    def threads_for(self, task_key: str) -> list[Thread]:
        return [t for t in self.all() if t.taskKey == task_key]

    @Slot(str, str, str, result=str)
    @Slot(str, str, str, str, result=str)
    @Slot(str, str, str, str, str, result=str)
    def spawn(self, task_key: str, preset_name: str, prompt: str, parent_id: str = "", title: str = "") -> str:
        preset = self.presets.get(preset_name)
        if not preset:
            raise ValueError(f"unknown preset {preset_name!r}")
        if preset.get("provider", "claude-code") != "claude-code":
            raise ValueError(f"provider {preset['provider']!r} not implemented yet")
        title = title or (prompt.strip().splitlines()[0][:60] if prompt.strip() else preset_name)
        meta = {"id": new_thread_id(), "title": title, "taskKey": task_key, "preset": preset["name"],
                "presetConfig": preset, "parentId": parent_id, "cwd": str(self.root), "createdAt": time.time(), "status": "starting"}
        t = Thread(self, meta)
        self._threads[t.id] = t
        t._log({"type": "harness.meta", **meta})
        self._persist_index()
        self._model.upsert(t.summary())
        self.threadsChanged.emit()
        t.start(prompt)
        return t.id

    @Slot(str, result=QObject)
    def get(self, thread_id: str):
        return self._threads.get(thread_id)

    @Slot(str, str)
    def send(self, thread_id: str, text: str):
        t = self._threads.get(thread_id)
        if t:
            t.send(text)

    @Slot(str)
    def stop(self, thread_id: str):
        t = self._threads.get(thread_id)
        if t:
            t.stop()

    def shutdown(self):
        """App exit: end child processes cleanly. Threads resume with --resume on next launch."""
        for t in self.all():
            if t._proc is not None:
                t._proc.shutdown()
                t._proc = None
                if t._status in ("starting", "working"):
                    t._status = "idle"
                    t.meta["status"] = "idle"
        self._persist_index()

    @Slot(result="QVariantList")
    def summaries(self):
        return [t.summary() for t in self.all()]

    def _thread_changed(self, t: Thread):
        self._model.upsert(t.summary())
        self._persist_index()
        self.threadsChanged.emit()

    def _thread_settled(self, t: Thread):
        self.threadSettled.emit(t.id)
        parent = self._threads.get(t.parentId)
        if parent is not None:
            summary = t.last_assistant_text().strip()
            note = f"child thread {t.id} ({t.title}) {t.status}" + (f": {summary[:500]}" if summary else "")
            parent.note(note)
            if parent.status in ("idle",) and getattr(cfg, "NOTIFY_PARENT_ON_CHILD_SETTLED", True):
                parent.send(f"[harness] {note}")
