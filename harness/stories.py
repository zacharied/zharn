"""Stories: the unit of work an author describes and validates (docs/AGENT-MODEL.md). This store
persists stories in the workspace, applies the pure state machine (harness/lifecycle.py), casts the
protagonist as a character with a live context, and delivers the author's comments to it.

This plan drives the main thread only; friends, minions, inbox delivery and recast come next."""
from __future__ import annotations

import json
import random
import string
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness import lifecycle as lc
from harness.fsutil import write_text_atomic
from harness.notify import intent
from harness.qmodels import DictListModel

STORY_ROLES = ["key", "title", "description", "priority", "phase", "ball", "needsYou", "flavor", "author", "protagonist",
               "castCount", "workingCount", "createdAt"]
WORKING = ("starting", "working")
VERBS_LOG_MAX = 200


def new_id(prefix: str) -> str:
    return prefix + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


def author_name(author: str, characters: dict[str, dict]) -> str:
    if author == "human":
        return "you"
    if author == "system":
        return "harness"
    ch = characters.get(author)
    return ch["name"] if ch else author


def needs_you_flavor(story: lc.Story, comments: list[dict]) -> str:
    if story.ball != "author" or story.author != "human":
        return ""
    pending = story.main.pending_yield
    kind = next((c["kind"] for c in comments if c["id"] == pending), "")
    if kind == "question":
        return "question"
    if kind == "handoff":
        return "outline ready" if story.phase == "planning" else "ready for review"
    return "waiting on you"


def render_brief(story: lc.Story, comments: list[dict], characters: dict[str, dict], role: dict, note: str) -> str:
    """Lifecycle spec §3.1: the story record as markdown, then the role's instructions, then the note."""
    out = [f"# {story.key}: {story.title}", "", story.description or "(no description)", "",
           f"Phase: {story.phase}" + (f" · ball: {story.ball}" if story.ball else ""), ""]
    if story.threads:
        out += ["## Threads", ""]
        for t in story.threads:
            label = "main" if t.id == story.main_thread else t.id
            out.append(f"### #{label} — author {author_name(t.author, characters)}, lead {author_name(t.lead, characters)}, turn: {t.turn}")
            for c in comments:
                if c["thread_id"] != t.id:
                    continue
                out.append(f"- **{author_name(c['author'], characters)}** ({c['kind']}): {c['body']}")
                opts = c.get("structured", {}).get("options")
                if opts:
                    out.append(f"  - options: {', '.join(opts)}")
            out.append("")
    recaps = [c for c in comments if c["kind"] == "recap"]
    if recaps:
        out += ["## Latest recap", "", recaps[-1]["body"], ""]
    cast = [ch for ch in characters.values() if ch["story_key"] == story.key]
    if cast:
        out += ["## Cast", ""] + [f"- {ch['name']} — {ch['role']}" + (" (protagonist)" if ch["id"] == story.protagonist else "") for ch in cast] + [""]
    if role.get("instructions"):
        out += ["## Instructions", role["instructions"], ""]
    if note:
        out += ["## Note", note]
    return "\n".join(out).rstrip() + "\n"


class StoryStore(QObject):
    storiesChanged = Signal()
    notifier = None

    def __init__(self, workspace, contexts, roles, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._contexts = contexts
        self._roles = roles
        self._stories: dict[str, lc.Story] = {}
        self._created: dict[str, float] = {}
        self._comments: dict[str, list[dict]] = {}
        self._characters: dict[str, dict] = {}
        self._model = DictListModel(STORY_ROLES, self)
        self.load_errors: list[str] = []
        self._load()
        contexts.contextsChanged.connect(self._refresh)

    # ---------------------------------------------------------------- persistence
    def _load(self):
        for key in self.workspace.story_keys():
            d = self.workspace.story_dir(key)
            try:
                data = json.loads((d / "story.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                self.load_errors.append(f"{key}: story.json unreadable ({e})")
                continue
            self._created[key] = data.pop("created", 0)
            self._stories[key] = lc.Story.from_dict(data)
            comments = []
            try:
                for line in (d / "threads.jsonl").read_text(encoding="utf-8").splitlines():
                    rec = json.loads(line)
                    if rec.get("type") == "comment":
                        rec.pop("type")
                        comments.append(rec)
            except (OSError, ValueError):
                pass
            self._comments[key] = comments
        try:
            self._characters = json.loads((self.workspace.local_dir / "characters.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._characters = {}
        self._refresh()

    def _save_story(self, key: str):
        s = self._stories[key]
        path = self.workspace.story_dir(key) / "story.json"
        write_text_atomic(path, json.dumps({**s.to_dict(), "created": self._created.get(key, 0)}, indent=1))

    def _append_record(self, key: str, record: dict):
        with (self.workspace.story_dir(key) / "threads.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _save_characters(self):
        write_text_atomic(self.workspace.local_dir / "characters.json", json.dumps(self._characters, indent=1))

    # ---------------------------------------------------------------- rows / queries
    def _row(self, key: str) -> dict:
        s = self._stories[key]
        cast = [ch for ch in self._characters.values() if ch["story_key"] == key]
        live = [self._contexts.get(ch["live_context"]) for ch in cast if ch.get("live_context")]
        flavor = needs_you_flavor(s, self._comments.get(key, []))
        return {"key": s.key, "title": s.title, "description": s.description, "priority": s.priority, "phase": s.phase,
                "ball": s.ball or "", "needsYou": bool(flavor), "flavor": flavor, "author": s.author,
                "protagonist": s.protagonist or "", "castCount": len(cast),
                "workingCount": sum(1 for c in live if c is not None and c.status in WORKING),
                "createdAt": self._created.get(key, 0), "mainThread": s.main_thread or "",
                "threads": [{"id": t.id, "n": i + 1, "isMain": t.id == s.main_thread, "author": t.author, "lead": t.lead,
                             "turn": t.turn, "pendingYield": t.pending_yield or ""} for i, t in enumerate(s.threads)]}

    def _refresh(self):
        self._model.reset([self._row(k) for k in self._stories])
        self.storiesChanged.emit()
        if self.load_errors and self.notifier is not None:
            for e in self.load_errors:
                self.notifier.error(e)
            self.load_errors.clear()

    def _key(self, key: str) -> str:
        for k in self._stories:
            if k.lower() == (key or "").lower():
                return k
        raise KeyError(key)

    def story(self, key: str) -> lc.Story | None:
        try:
            return self._stories[self._key(key)]
        except KeyError:
            return None

    @Property(QObject, constant=True)
    def model(self): return self._model

    @Slot(str, result="QVariantMap")
    def get(self, key):
        try:
            return self._row(self._key(key))
        except KeyError:
            return {}

    @Slot(result="QVariantList")
    def list(self):
        return [self._row(k) for k in self._stories]

    @Slot(str, result="QVariantList")
    def comments(self, key):
        try:
            key = self._key(key)
        except KeyError:
            return []
        return [{**c, "authorName": author_name(c["author"], self._characters)} for c in self._comments.get(key, [])]

    @Slot(str, result="QVariantList")
    def cast(self, key):
        try:
            key = self._key(key)
        except KeyError:
            return []
        out = []
        for ch in self._characters.values():
            if ch["story_key"] == key:
                ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
                out.append({**ch, "contextStatus": ctx.status if ctx is not None else "none"})
        return out

    @Slot(str, result="QVariantMap")
    def character(self, character_id):
        return dict(self._characters[character_id]) if character_id in self._characters else None

    # ---------------------------------------------------------------- the one way state changes
    def _apply(self, key: str, action) -> dict:
        s = self._stories[key]
        s2, comment = lc.step(s, action, comment_id=new_id("cmt_"), now=time.time())
        lc.check_invariants(s2)
        self._stories[key] = s2
        for t in s2.threads:
            if not any(t.id == old.id for old in s.threads):
                self._append_record(key, {"type": "thread", "id": t.id, "author": t.author, "lead": t.lead, "opened_at": comment["created_at"]})
        self._comments.setdefault(key, []).append(comment)
        self._append_record(key, {"type": "comment", **comment})
        self._save_story(key)
        self._refresh()
        flavor = needs_you_flavor(s2, self._comments[key])
        if flavor and self.notifier is not None:
            self.notifier.info(f"{key} needs you: {flavor}")
        return comment

    def _protagonist_context(self, key: str):
        s = self._stories[key]
        ch = self._characters.get(s.protagonist or "")
        return self._contexts.get(ch["live_context"]) if ch and ch.get("live_context") else None

    def _deliver(self, key: str, comment: dict, phase_before: str):
        """Main thread only: tell the protagonist what the author just did."""
        ctx = self._protagonist_context(key)
        if ctx is None:
            return
        s = self._stories[key]
        ch = self._characters.get(s.protagonist or "")
        role_cfg = self._roles.get(ch["role"]) if ch else None
        if ch is not None and role_cfg:
            ctx.meta["systemPrompt"] = self._system_prompt(s, ch, role_cfg)
        kind = "reply" if comment.get("reply_to") else ("comment" if comment["kind"] == "text" else comment["kind"])
        text = f"[{author_name(comment['author'], self._characters)}] {kind} in #{comment['thread_id']}: {comment['body']}"
        phase = s.phase
        if phase != phase_before:
            text += f"\nPhase is now {phase}."
        ctx.send(text)

    # ---------------------------------------------------------------- author intents
    @Slot(str, str, result=str)
    @intent
    def create(self, title, description=""):
        key = self.workspace.next_key()
        self._stories[key] = lc.Story(key=key, title=title, description=description, phase="todo")
        self._created[key] = time.time()
        self._comments[key] = []
        self.workspace.story_dir(key)
        self._save_story(key)
        self._refresh()
        return key

    @Slot(str, str, str)
    @intent
    def update(self, key, title, description):
        key = self._key(key)
        s = self._stories[key]
        if s.phase not in lc.UNSTARTED:
            raise lc.Rejected(f"{key} is already started; the description is fixed")
        s.title, s.description = title, description
        self._save_story(key)
        self._refresh()

    @Slot(str, str, str, result=str)
    @intent
    def start(self, key, note="", role=""):
        key = self._key(key)
        role_name = role or getattr(cfg, "DEFAULT_ROLE", "protagonist")
        role_cfg = self._roles.get(role_name)
        if not role_cfg:
            raise ValueError(f"unknown role {role_name!r}")
        provider = role_cfg.get("provider", "claude-code")
        if provider != "claude-code":
            raise ValueError(f"role {role_name!r} uses provider {provider!r}, which is not implemented yet")
        taken = {ch["name"] for ch in self._characters.values() if ch["story_key"] == key}
        name, n = role_cfg["name"], 2
        while name in taken:
            name, n = f"{role_cfg['name']}-{n}", n + 1
        chr_id, thread_id = new_id("chr_"), new_id("thr_")
        prev_story = self._stories[key]
        prev_comments = list(self._comments.get(key, []))
        self._apply(key, lc.Start(thread_id=thread_id, protagonist=chr_id, note=note, role=role_cfg["name"]))
        ch = {"id": chr_id, "story_key": key, "role": role_cfg["name"], "name": name, "live_context": None,
              "attention": thread_id, "inbox": [], "recaps": [], "verbs_log": []}
        self._characters[chr_id] = ch
        s = self._stories[key]
        try:
            cid = self._contexts.create(role_cfg["name"], story_key=key, owner=chr_id, title=f"{key} · {name}",
                                        system_prompt=self._system_prompt(s, ch, role_cfg),
                                        env={"HARNESS_CHARACTER_ID": chr_id})
        except Exception:
            # Belt and braces: the provider check above should already have caught this, but if
            # context creation still fails, don't leave the story wedged in planning with a
            # protagonist that has no context (and no way to Start again).
            self._stories[key] = prev_story
            self._comments[key] = prev_comments
            self._save_story(key)
            del self._characters[chr_id]
            self._refresh()
            raise
        ch["live_context"] = cid
        self._save_characters()
        self._contexts.get(cid).send(render_brief(s, self._comments[key], self._characters, role_cfg, note))
        self._refresh()
        return chr_id

    def _system_prompt(self, s: lc.Story, ch: dict, role_cfg: dict) -> str:
        rule = getattr(cfg, "OUTLINE_RULE_REQUIRED", "") if role_cfg.get("outline_first") else getattr(cfg, "OUTLINE_RULE_OPTIONAL", "")
        return getattr(cfg, "CHARACTER_SYSTEM_PROMPT", "").format(
            name=ch["name"], character_id=ch["id"], story_key=s.key, title=s.title, phase=s.phase,
            thread_id=s.main_thread or "", outline_rule=rule)

    def _author_action(self, key, action, *, resume: bool):
        key = self._key(key)
        before = self._stories[key].phase
        comment = self._apply(key, action)
        if resume:
            self._deliver(key, comment, before)
        return comment

    @Slot(str, str)
    @intent
    def proceed(self, key, note=""):
        self._author_action(key, lc.Proceed(by="human", note=note), resume=True)

    @Slot(str, str)
    @intent
    def approve(self, key, note=""):
        self._author_action(key, lc.Approve(note=note), resume=False)

    @Slot(str, str)
    @intent
    def backToPlanning(self, key, note=""):
        self._author_action(key, lc.BackToPlanning(note=note), resume=True)

    @Slot(str, str)
    @intent
    def cancel(self, key, note=""):
        key = self._key(key)
        self._author_action(key, lc.Cancel(note=note), resume=False)
        for ch in self._characters.values():
            if ch["story_key"] == key and ch.get("live_context"):
                ctx = self._contexts.get(ch["live_context"])
                if ctx is not None:
                    ctx.stop()
        self._refresh()

    @Slot(str, str)
    @intent
    def reopen(self, key, note=""):
        self._author_action(key, lc.Reopen(note=note), resume=True)

    @Slot(str, str, result="QVariantMap")
    @Slot(str, str, str, result="QVariantMap")
    @intent
    def resolve(self, key, thread_id, note=""):
        """Close a side thread waiting on the author: nobody is resumed or notified (§2.1)."""
        key = self._key(key)
        comment = self._author_action(key, lc.Resolve(thread_id=thread_id, by="human", note=note), resume=False)
        self._clear_attention(key, thread_id)
        return comment

    @Slot(str, str, result="QVariantMap")
    @Slot(str, str, str, result="QVariantMap")
    @intent
    def comment(self, key, body, thread_id=""):
        key = self._key(key)
        s = self._stories[key]
        tid = thread_id or s.main_thread or ""
        return self._author_action(key, lc.Comment(thread_id=tid, by="human", body=body), resume=True)

    # ---------------------------------------------------------------- cast verbs (via IPC)
    def _char(self, character_id: str) -> tuple[str, dict]:
        ch = self._characters[character_id]  # KeyError for unknown characters
        return ch["story_key"], ch

    def cast_yield(self, character_id, kind, body, options=(), thread_id="", checks=()) -> dict:
        key, ch = self._char(character_id)
        tid = thread_id or ch.get("attention") or self._stories[key].main_thread
        return self._apply(key, lc.Yield(thread_id=tid, by=character_id, kind=kind, body=body, options=list(options),
                                         checks=[dict(c) for c in checks]))

    def cast_proceed(self, character_id, note="") -> dict:
        key, ch = self._char(character_id)
        role_cfg = self._roles.get(ch["role"]) or {}
        outline_approved_transition = {"from": ["planning", "author"], "to": ["implementing", "cast"]}
        if role_cfg.get("outline_first") and not any(
                c.get("structured", {}).get("transition") == outline_approved_transition
                for c in self._comments.get(key, [])):
            raise lc.Rejected("your role requires an approved outline first: `yield --handoff` the outline and wait for Proceed")
        return self._apply(key, lc.Proceed(by=character_id, note=note))

    def cast_resolve(self, character_id, thread_id, note="") -> dict:
        key, ch = self._char(character_id)
        if not thread_id:
            raise lc.Rejected("resolve needs an explicit --thread")
        c = self._apply(key, lc.Resolve(thread_id=thread_id, by=character_id, note=note))
        self._clear_attention(key, thread_id)
        return c

    def _clear_attention(self, key: str, thread_id: str):
        """A lead attending a just-resolved thread comes up for air (§2.1 Resolve)."""
        lead = self._stories[key].thread(thread_id).lead
        ch = self._characters.get(lead)
        if ch is not None and ch.get("attention") == thread_id:
            ch["attention"] = None
            self._save_characters()

    def cast_recap(self, character_id, body) -> dict:
        key, ch = self._char(character_id)
        c = self._apply(key, lc.Recap(by=character_id, body=body))
        ch.setdefault("recaps", []).append(c["id"])
        self._save_characters()
        return c

    def cast_comment(self, character_id, body, thread_id="") -> dict:
        key, ch = self._char(character_id)
        tid = thread_id or ch.get("attention") or self._stories[key].main_thread
        return self._apply(key, lc.Comment(thread_id=tid, by=character_id, body=body))

    def log_verb(self, character_id, verb, args: dict, ok: bool, error: str = ""):
        ch = self._characters.get(character_id)
        if ch is None:
            return
        log = ch.setdefault("verbs_log", [])
        log.append({"verb": verb, "args": dict(args), "ok": ok, "error": error, "ts": time.time()})
        if len(log) > VERBS_LOG_MAX:
            del log[:len(log) - VERBS_LOG_MAX]
        self._save_characters()
