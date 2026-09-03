"""Contexts: one agent conversation each — system prompt, turns, tool calls — resumable and
viewable. Owned by a character, a minion, or the human (a *bare* context with no story).
What bb calls a thread (docs/AGENT-MODEL.md §2). Transcripts persist as JSONL under the
workspace's local dir."""
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
from harness.fsutil import write_text_atomic
from harness.notify import intent
from harness.qmodels import DictListModel

CONTEXT_ROLES = ["id", "title", "storyKey", "owner", "status", "roleName", "costUsd", "turns", "createdAt"]
SETTLED = ("idle", "failed", "stopped")


def _has_text_block(ev: dict) -> bool:
    """A replayed user message (claude's --replay-user-messages echo), as opposed to a tool_result."""
    content = (ev.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content)
    return any(isinstance(b, dict) and b.get("type") == "text" for b in content or [])


def new_context_id() -> str:
    return "ctx_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


class Context(QObject):
    changed = Signal()

    def __init__(self, store: "ContextStore", meta: dict):
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
        self._proc_cwd: str | None = None
        self._retired: list[ClaudeCodeProcess] = []  # released processes, kept alive (and referenced) until they exit
        self._unacked = 0  # messages pushed to the process that claude has not echoed (consumed) yet
        self._log_path = store.data_dir / f"{meta['id']}.jsonl"

    # ---------------------------------------------------------------- QML-facing state
    @Property(str, constant=True)
    def id(self): return self.meta["id"]

    @Property(str, notify=changed)
    def title(self): return self.meta.get("title", "")

    @Property(str, constant=True)
    def storyKey(self): return self.meta.get("storyKey", "")

    @Property(str, constant=True)
    def owner(self): return self.meta.get("owner", "human")

    @Property(str, constant=True)
    def roleName(self): return self.meta.get("role", "")

    @Property(str, notify=changed)
    def status(self): return self._status

    @Property(str, notify=changed)
    def sessionId(self): return self._interp.session_id

    @Property(str, notify=changed)
    def model(self): return self._interp.model_name or self.meta.get("roleConfig", {}).get("model", "")

    @Property(float, notify=changed)
    def costUsd(self): return self._interp.cost_usd

    @Property(int, notify=changed)
    def turns(self): return self._interp.turns

    @Property(str, notify=changed)
    def lastError(self): return self._last_error

    @Property("QVariantMap", constant=True)
    def about(self): return self.meta.get("about") or {}   # asides: {story_key, comment_id}

    @Property(QObject, constant=True)
    def transcriptModel(self): return self.transcript

    @property
    def notifier(self): return getattr(self._store, "notifier", None)

    @property
    def proc_cwd(self) -> str | None:
        return self._proc_cwd if self._proc is not None else None

    def last_assistant_text(self) -> str:
        for row in reversed(self.transcript.rows()):
            if row["role"] == "assistant" and row["kind"] == "text" and row["text"].strip():
                return row["text"]
        return ""

    def summary(self) -> dict:
        return {"id": self.id, "title": self.title, "storyKey": self.storyKey, "owner": self.owner, "status": self._status,
                "roleName": self.roleName, "costUsd": round(self._interp.cost_usd, 4), "turns": self._interp.turns,
                "createdAt": self.meta.get("createdAt", 0), "sessionId": self._interp.session_id, "model": self.model,
                "predecessor": self.meta.get("predecessor"), "forkedFrom": self.meta.get("forkedFrom"),
                "about": self.meta.get("about"),
                "lastText": self.last_assistant_text()}

    # ---------------------------------------------------------------- lifecycle
    def _set_status(self, status: str):
        if status != self._status:
            self._status = status
            self.meta["status"] = status
            self._store._context_changed(self)
            if status in SETTLED:
                self._store.contextSettled.emit(self.id)
        self.changed.emit()

    def _log(self, record: dict):
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _env(self, extra: dict | None = None) -> dict:
        # PYTHONPATH: `python -m harness.cli` otherwise resolves `harness` via whatever's on sys.path for its cwd
        # (an editable install elsewhere, in a worktree) rather than the code this app is actually running.
        env = {"HARNESS_CONTEXT_ID": self.id, "HARNESS_STORY_KEY": self.storyKey, "HARNESS_ROOT": str(self._store.root),
               "HARNESS_WORKSPACE": str(self._store.workspace_dir), "HARNESS_CLI": f"{sys.executable} -m harness.cli",
               "PYTHONPATH": str(self._store.root)}
        env.update(self.meta.get("env") or {})
        env.update(extra or {})
        env.update(self._store.extra_env())
        return env

    def _system_prompt(self) -> str:
        role = self.meta.get("roleConfig", {})
        base = self.meta.get("systemPrompt") or getattr(cfg, "BARE_CONTEXT_SYSTEM_PROMPT", "").format(context_id=self.id)
        return "\n\n".join(p for p in (base, role.get("instructions", "")) if p)

    def _spawn(self, resume: str = ""):
        role = self.meta.get("roleConfig", {})
        extra = list(getattr(cfg, "EFFORT_FLAGS", {}).get(role.get("reasoning", ""), []))
        if not resume and self.meta.get("forkSession"):
            resume, extra = self.meta["forkSession"], extra + ["--fork-session"]  # first turn of a fork only
        cwd, place_env = self._store.placement(self)   # decided at every spawn, not at creation (workspace spec §4.5)
        self._proc_cwd = cwd
        self._proc = ClaudeCodeProcess(cwd=cwd, env=self._env(place_env),
                                       model=role.get("model", ""), permission=role.get("permission", "auto"),
                                       resume=resume, system_prompt=self._system_prompt(), extra_args=extra)
        self._proc.event.connect(self._on_event)
        self._proc.stderrText.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.start()

    @Slot(str)
    @intent
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
        self._unacked += 1
        self._proc.send_user(text)

    @Slot()
    @intent
    def stop(self):
        if self._proc and self._proc.running():
            self._proc.stop()
            self._unacked = 0
            self._set_status("stopped")

    def recycle(self):
        """Drop an idle process so the next send resumes the session in a fresh one — the way a character
        changes working directory between turns. A working process is left alone. The old process is released
        asynchronously (never blocks the GUI thread) but kept referenced in self._retired until it actually
        exits, so Qt doesn't destroy a still-running QProcess out from under us."""
        if self._proc is None or self._status in ("starting", "working"):
            return
        old, self._proc = self._proc, None
        for sig, slot in ((old.event, self._on_event), (old.stderrText, self._on_stderr), (old.finished, self._on_finished)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._retired.append(old)
        old.finished.connect(lambda *_: self._retired.remove(old) if old in self._retired else None)
        old.release()
        self.changed.emit()

    def _on_event(self, ev: dict):
        self._log(ev)
        if ev.get("type") == "user" and _has_text_block(ev):
            self._unacked = max(0, self._unacked - 1)   # claude echoed a pushed message: it has been consumed
        hint = self._interp.apply(ev)
        if hint == "idle" and self._unacked > 0:
            hint = "working"                             # a pushed message is still queued: not a turn end
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
        self._unacked = 0
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
            elif rec.get("type") != "harness.meta":
                self._interp.apply(rec)
        for row in self.transcript.rows():
            row["streaming"] = False
        if self._status in ("starting", "working"):
            self._status = "idle"

    def note(self, text: str):
        """A harness note in the transcript (delivery notices etc.)."""
        self._log({"type": "harness.note", "text": text, "ts": time.time()})
        self.transcript.append(role="system", kind="note", text=text)


class ContextStore(QObject):
    contextsChanged = Signal()
    contextSettled = Signal(str)
    revealChanged = Signal()   # the Contexts panel should select revealTarget (e.g. a fresh aside)
    notifier = None

    def __init__(self, root: Path, data_dir: Path, roles, workspace_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._reveal = ""
        self.root = root
        self.data_dir = Path(data_dir)
        self.workspace_dir = Path(workspace_dir) if workspace_dir else root
        self.roles = roles
        self.extra_env = lambda: {}
        self.placement = lambda c: (c.meta.get("cwd") or str(self.workspace_dir), {})   # StoryStore overrides (spec §4.5)
        self._contexts: dict[str, Context] = {}
        self._model = DictListModel(CONTEXT_ROLES, self)
        self._load()

    @Property(QObject, constant=True)
    def model(self): return self._model

    def _load(self):
        try:
            metas = json.loads((self.data_dir / "index.json").read_text())
        except (OSError, ValueError):
            metas = []
        for meta in metas:
            c = Context(self, meta)
            c.replay()
            self._contexts[c.id] = c
        self._model.reset([c.summary() for c in self.all()])

    def _persist_index(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        write_text_atomic(self.data_dir / "index.json", json.dumps([c.meta for c in self.all()], indent=1))

    def all(self) -> list[Context]:
        return sorted(self._contexts.values(), key=lambda c: c.meta.get("createdAt", 0))

    def contexts_for(self, story_key: str) -> list[Context]:
        return [c for c in self.all() if c.storyKey == story_key]

    def create(self, role_name: str, *, story_key: str = "", owner: str = "human", title: str = "", system_prompt: str = "",
               env: dict | None = None, cwd: str = "", predecessor: str | None = None, forked_from: str | None = None,
               about: dict | None = None, fork_session: str = "") -> str:
        role = self.roles.get(role_name)
        if not role:
            raise ValueError(f"unknown role {role_name!r}")
        if role.get("provider", "claude-code") != "claude-code":
            raise ValueError(f"provider {role['provider']!r} not implemented yet")
        meta = {"id": new_context_id(), "title": title or role["name"], "storyKey": story_key, "owner": owner,
                "role": role["name"], "roleConfig": role, "predecessor": predecessor, "forkedFrom": forked_from,
                "forkSession": fork_session, "about": dict(about) if about else None,
                "cwd": cwd or str(self.workspace_dir), "env": dict(env or {}), "systemPrompt": system_prompt,
                "createdAt": time.time(), "status": "idle"}
        c = Context(self, meta)
        self._contexts[c.id] = c
        c._log({"type": "harness.meta", **meta})
        self._persist_index()
        self._model.upsert(c.summary())
        self.contextsChanged.emit()
        return c.id

    def spawn(self, role_name: str, prompt: str, **create_kwargs) -> str:
        if not create_kwargs.get("title"):
            create_kwargs["title"] = prompt.strip().splitlines()[0][:60] if prompt.strip() else role_name
        cid = self.create(role_name, **create_kwargs)
        self._contexts[cid].send(prompt)
        return cid

    def fork(self, source_id: str, *, role_name: str, owner: str = "human", story_key: str = "", title: str = "",
             system_prompt: str = "", env: dict | None = None, about: dict | None = None) -> str:
        """A context that starts knowing everything `source_id` knows (lifecycle spec §3.5): its first turn
        resumes the source's session with --fork-session, later turns resume its own. Shared by asides and
        `call --fork`. The source keeps running on its own session, untouched."""
        src = self._contexts.get(source_id)
        if src is None:
            raise KeyError(source_id)
        if not src.sessionId:
            raise ValueError(f"{source_id} has never run; nothing to fork")
        if src.status in ("starting", "working"):
            raise ValueError(f"{source_id} is working; fork it when it stops")
        return self.create(role_name, story_key=story_key, owner=owner, title=title or f"fork of {src.title}",
                           system_prompt=system_prompt, env=env, cwd=src.meta.get("cwd", ""),
                           forked_from=source_id, fork_session=src.sessionId, about=about)

    @Slot(str, result=str)
    @intent
    def newBare(self, role_name: str) -> str:
        return self.create(role_name or getattr(cfg, "DEFAULT_BARE_ROLE", "claude-default"), title="New context")

    @Slot(str, result=QObject)
    def get(self, cid: str):
        return self._contexts.get(cid)

    @Slot(str, str)
    @intent
    def send(self, cid: str, text: str):
        c = self._contexts.get(cid)
        if c:
            c.send(text)

    @Slot(str)
    @intent
    def stop(self, cid: str):
        c = self._contexts.get(cid)
        if c:
            c.stop()

    def shutdown(self):
        """App exit: end child processes cleanly (blocking is fine here). Contexts resume with --resume on
        next launch. Also finishes off any processes a recycle() released but that haven't exited yet."""
        for c in self.all():
            if c._proc is not None:
                c._proc.shutdown()
                c._proc = None
                if c._status in ("starting", "working"):
                    c._status = "idle"
                    c.meta["status"] = "idle"
            for p in list(c._retired):
                if p.running():
                    p.shutdown()
        self._persist_index()

    @Property(str, notify=revealChanged)
    def revealTarget(self): return self._reveal

    @Slot(str)
    def reveal(self, cid: str):
        """Ask the Contexts panel to select a context (empty = consumed). UI plumbing, not state."""
        self._reveal = cid
        self.revealChanged.emit()

    @Slot(result="QVariantList")
    def summaries(self):
        return [c.summary() for c in self.all()]

    def _context_changed(self, c: Context):
        self._model.upsert(c.summary())
        self._persist_index()
        self.contextsChanged.emit()
