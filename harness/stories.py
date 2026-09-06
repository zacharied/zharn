"""Stories: the unit of work an author describes and validates (docs/AGENT-MODEL.md). This store
persists stories in the workspace, applies the pure state machine (harness/lifecycle.py), casts the
protagonist as a character with a live context, and delivers the author's comments to it.

This plan drives the main thread only; friends, minions, inbox delivery and recast come next."""
from __future__ import annotations

import json
import random
import re
import string
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness import lifecycle as lc
from harness import skills
from harness.contexts import context_lines
from harness.environments import EnvError, EnvironmentStore, register_repo
from harness.fsutil import write_text_atomic
from harness.notify import intent
from harness.qmodels import DictListModel

STORY_ROLES = ["key", "title", "description", "priority", "phase", "ball", "needsYou", "flavor", "author", "protagonist",
               "castCount", "workingCount", "createdAt", "repos", "environments"]
WORKING = ("starting", "working")
VERBS_LOG_MAX = 200
FRIEND_POSITION = "friend"   # what `call` and the composer's /call cast into; nobody picks it (spec §1)


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
    """Spec §2.4 needs-you: the ball with the human, or any human-authored side thread waiting on them."""
    if story.author != "human":
        return ""
    if story.ball == "author":
        pending = story.main.pending_yield
        kind = next((c["kind"] for c in comments if c["id"] == pending), "")
        if kind == "question":
            return "question"
        if kind == "handoff":
            return "outline ready" if story.phase == "planning" else "ready for review"
        return "waiting on you"
    if any(t.author == "human" and t.turn == "author" and t.id != story.main_thread for t in story.threads):
        return "a side thread waits on you"
    return ""


def render_brief(story: lc.Story, comments: list[dict], characters: dict[str, dict], note: str, *,
                 substories: list[dict] = (), situation: str = "", skill: str = "") -> str:
    """Lifecycle spec §3.1: the story record as markdown, the situation (recasts), the note, then the skill due for its position.
    The position's instructions and the contract are in the system prompt (§5.3), not here."""
    out = [f"# {story.key}: {story.title}", "", story.description or "(no description)", "",
           f"Phase: {story.phase}" + (f" · ball: {story.ball}" if story.ball else ""), ""]
    if story.parent_story:
        out += [f"Sub-story of {story.parent_story}; its author is {author_name(story.author, characters)}.", ""]
    if story.threads:
        out += ["## Threads", ""]
        for t in story.threads:
            out.append(f"### #{lc.thread_label(story, t.id)} — author {author_name(t.author, characters)}, lead {author_name(t.lead, characters)}, turn: {t.turn}")
            for c in comments:
                if c["thread_id"] != t.id:
                    continue
                out.append(f"- **{author_name(c['author'], characters)}** ({c['kind']}): {c['body']}")
                for line in lc.question_lines(c.get("structured", {}).get("questions") or []):
                    out.append(f"  {line}")
            out.append("")
    latest = {}
    for c in comments:
        if c["kind"] == "recap":
            latest[c["author"]] = c
    if latest:
        out += ["## Recaps (latest per character)", ""] + [f"**{author_name(a, characters)}**: {c['body']}" for a, c in latest.items()] + [""]
    cast = [ch for ch in characters.values() if ch["story_key"] == story.key]
    if cast:
        out += ["## Cast", ""] + [f"- {ch['name']} — {ch['position']}" + (" (protagonist)" if ch["id"] == story.protagonist else "") for ch in cast] + [""]
    if substories:
        out += ["## Sub-stories", ""] + [f"- {x['key']}: {x['title']} ({x['phase']}" + (f", ball {x['ball']}" if x['ball'] else "") + ")"
                                        for x in substories] + [""]
    if situation:
        out += ["## Situation", situation, ""]
    if note:
        out += ["## Note", note]
    if skill:
        out += ["", skill]
    return "\n".join(out).rstrip() + "\n"


class StoryStore(QObject):
    storiesChanged = Signal()
    notifier = None

    def __init__(self, workspace, contexts, casting, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._contexts = contexts
        self._casting = casting
        self._stories: dict[str, lc.Story] = {}
        self._created: dict[str, float] = {}
        self._comments: dict[str, list[dict]] = {}
        self._characters: dict[str, dict] = {}
        self._model = DictListModel(STORY_ROLES, self)
        self.load_errors: list[str] = []
        self.environments = EnvironmentStore(workspace, self._parent_of)   # _load()'s _refresh() needs this to exist
        contexts.placement = self._placement   # Task 5 makes ContextStore call it at every spawn
        contexts.system_prompt = self.system_prompt   # the stable character prompt, composed at every spawn (spec §5.3)
        self._load()
        contexts.contextsChanged.connect(self._refresh)
        contexts.contextSettled.connect(self._on_turn_end)
        contexts.contextUsage.connect(self._on_usage)

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
        for key in self._stories:
            self._sweep_environments(key)   # §4.8: a worktree a failed remove left behind is swept at the next load
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
                "parentStory": s.parent_story or "",
                "repos": list(s.repos), "environments": self._env_rows(key),
                "openSubstories": sum(1 for x in self._stories.values() if x.parent_story == s.key and x.phase not in lc.TERMINAL),
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

    def _parent_of(self, key: str) -> str | None:
        return self._stories[key].parent_story

    def _env_rows(self, key: str) -> list[dict]:
        """One row per live environment; `into` is the branch this story's branch lands in (workspace spec §4.8)."""
        return [{"repo": r["repo"], "path": r["path"], "branch": r["branch"], "parent": r["parent"],
                 "into": self.environments.target(r)} for r in self.environments.records(key)]

    def _placement(self, ctx) -> tuple[str, dict]:
        """§4.5: a character's context runs in its environment's path, else where its meta says (the workspace dir).
        A worktree deleted out from under a live character (by hand, or before `env open` re-creates it) must not
        strand its turn: fall back to the workspace dir rather than spawn into a path that no longer exists."""
        ch = self._characters.get(ctx.meta.get("owner", ""))
        repo = ch.get("environment") if ch else None
        rec = self.environments.get(ch["story_key"], repo) if repo else None
        if rec is not None and Path(rec["path"]).is_dir():
            return rec["path"], {"HARNESS_REPO": repo, "HARNESS_ENV": rec["path"]}
        return ctx.meta.get("cwd") or str(self.workspace.dir), {}

    def environment_line(self, ch: dict) -> str:
        repo = ch.get("environment")
        rec = self.environments.get(ch["story_key"], repo) if repo else None
        if rec is not None and not rec.get("removed") and Path(rec["path"]).is_dir():
            return f"in {repo} at {rec['path']} (your story's worktree, branch {rec['branch']})"
        return f"in the workspace dir {self.workspace.dir}; run `env open <repo>` before touching a repo"

    def _awaits_line(self, ch: dict) -> str:
        """The threads and sub-stories a character awaits, formatted for a message: threads get a leading #,
        sub-story keys (bare) do not."""
        return ", ".join(("#" + a) if a.startswith("thr_") else a for a in self.awaits(ch)) or "nothing"

    def _owes_line(self, ch: dict) -> str:
        s = self._stories[ch["story_key"]]
        return ", ".join("#" + lc.thread_label(s, t) for t in self.owes(ch)) or "nothing"

    def _where(self, ch: dict, thread_id: str) -> str:
        """A thread named to a character: `#main` or `#thr_…`, with ` of KEY` when it belongs to another story."""
        skey, _ = self._thread_anywhere(thread_id)
        if skey is None:
            return f"#{thread_id}"
        return f"#{lc.thread_label(self._stories[skey], thread_id)}" + (f" of {skey}" if skey != ch["story_key"] else "")

    # ---------------------------------------------------------------- context usage (spec §2.3)
    def recap_due(self, ch: dict) -> bool:
        """Past the warn line with no recap since the crossing."""
        warned = ch.get("context_warned")
        return warned is not None and len(ch.get("recaps", [])) <= warned

    def _thresholds(self, ctx) -> tuple[int, int]:
        """The warn and max lines for this context's window (`contexts.context_lines`, the meter's frame)."""
        return context_lines(getattr(ctx, "contextWindow", 0) or 0)

    def _nudge(self, ch: dict, ctx, text: str):
        """A harness line into a live context mid-turn, dressed like a delivery: the situation line, then `[harness] …`."""
        ctx.send(self.situation(ch) + f"\n[harness] {text}")

    def _on_usage(self, context_id: str):
        """A context's reading moved. Each line is crossed once per context, only mid-turn: warn asks for a recap and
        the situation line says `recap due` until one lands; max asks the character to finish the step in hand and
        marks a recast for the turn boundary (§3.4)."""
        ch = self._character_by_context(context_id)
        if ch is None:
            return
        s = self._stories[ch["story_key"]]
        ctx = self._contexts.get(context_id)
        if s.phase in lc.TERMINAL or ctx is None or ctx.status not in WORKING:
            return
        tokens = getattr(ctx, "contextTokens", 0) or 0
        warn, limit = self._thresholds(ctx)
        where = self._where(ch, ch.get("attention") or s.main_thread)
        if tokens >= warn and ch.get("context_warned") is None:
            ch["context_warned"] = len(ch.get("recaps", []))
            self._nudge(ch, ctx, f"context past the warn line: post a `recap` in {where} now — "
                                 "your successor is built from the story record and that recap.")
        if tokens >= limit and not ch.get("context_maxed"):
            ch["context_maxed"] = True
            ch.setdefault("recast_pending", {"model": "", "effort": "", "preset": "", "cause": "context"})   # a manual one keeps its picks
            self._nudge(ch, ctx, f"context at the limit: finish the step in hand and post a `recap` in {where} now. "
                                 "You are recast when this turn ends.")
        self._save_characters()
        self._refresh()

    def situation(self, ch: dict) -> str:
        """Spec §5.3: the volatile facts — one line at the top of every message, never in the system prompt."""
        s = self._stories[ch["story_key"]]
        return (f"[situation] phase {s.phase} · attending {self._where(ch, ch.get('attention') or s.main_thread)} · you owe {self._owes_line(ch)} · "
                f"you await {self._awaits_line(ch)} · {self.environment_line(ch)}"
                + (" · recap due" if self.recap_due(ch) else ""))

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
        out = []
        for c in self._comments.get(key, []):
            aside = self._aside_for(c["id"])
            out.append({**c, "authorName": author_name(c["author"], self._characters), "asideId": aside,
                        "asideEnabled": bool(aside) or bool(self.aside_source(key, c))})
        return out

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
                out.append({**ch, "contextStatus": ctx.status if ctx is not None else "none", "status": self.status(ch),
                            "owes": self.owes(ch), "awaits": self.awaits(ch), "inboxDepth": len(ch.get("inbox", [])), "recapDue": self.recap_due(ch),
                            "forkedFrom": ch.get("forked_from") or "", "environment": ch.get("environment") or ""})
        return out

    # ---------------------------------------------------------------- derived character state (spec §1)
    def owes(self, ch: dict) -> list[str]:
        return [t.id for t in lc.owes(self._stories[ch["story_key"]], ch["id"])]

    def awaits(self, ch: dict) -> list[str]:
        threads = [t.id for t in lc.awaits(self._stories[ch["story_key"]], ch["id"])]
        subs = [k for k, s in self._stories.items() if s.author == ch["id"] and s.ball == "cast"]
        return threads + subs

    def status(self, ch: dict) -> str:
        if self._stories[ch["story_key"]].phase in lc.TERMINAL:
            return "retired"
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        if ctx is not None and ctx.status in WORKING:
            return "working"
        return "waiting" if self.awaits(ch) else "idle"

    @Slot(str, result="QVariantMap")
    def character(self, character_id):
        ch = self._characters.get(character_id)
        return {**ch, "recapDue": self.recap_due(ch)} if ch is not None else None

    # ---------------------------------------------------------------- the one way state changes
    def _apply(self, key: str, action, extra: dict | None = None) -> dict:
        s = self._stories[key]
        s2, comment = lc.step(s, action, comment_id=new_id("cmt_"), now=time.time())
        writer = self._characters.get(comment["author"])
        if writer is not None:  # spec §4: which memory wrote it (characters only)
            comment["context"] = writer.get("live_context")
        if extra:
            comment["structured"].update(extra)
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

    # ---------------------------------------------------------------- routing (spec §3.2) and delivery (§2.3)
    def _mentions(self, key: str, body: str) -> list[str]:
        names = {ch["name"].lower(): ch["id"] for ch in self._characters.values() if ch["story_key"] == key}
        out = []
        for m in re.findall(r"@([\w-]+)", body or ""):
            cid = names.get(m.lower())
            if cid and cid not in out:
                out.append(cid)
        return out

    def _by_name(self, key: str, name: str) -> dict:
        for ch in self._characters.values():
            if ch["story_key"] == key and ch["name"].lower() == name.lower():
                return ch
        raise lc.Rejected(f"no character named {name!r} on {key}")

    def _comment_by_id(self, comment_id: str) -> dict | None:
        for comments in self._comments.values():
            for c in comments:
                if c["id"] == comment_id:
                    return c
        return None

    def addressees(self, key: str, comment: dict) -> list[str]:
        """Who a comment is addressed to: a yield → the thread's author; a reply to a yield → whoever yielded (the
        lead, when the harness did); anything else → the lead; plus @mentions; never the comment's own author."""
        s = self._stories[key]
        t = s.thread(comment["thread_id"])
        if comment["kind"] in lc.YIELD_KINDS:
            target = t.author
        elif comment.get("reply_to"):
            pending = self._comment_by_id(comment["reply_to"])
            target = pending["author"] if pending and pending["author"] in self._characters else t.lead
        else:
            target = t.lead
        out = []
        for cid in [target] + self._mentions(key, comment["body"]):
            if cid in self._characters and cid != comment["author"] and cid not in out:
                out.append(cid)
        return out

    def _format(self, ch: dict, comment: dict) -> str:
        kind = "reply" if comment.get("reply_to") else ("comment" if comment["kind"] == "text" else comment["kind"])
        text = f"[{author_name(comment['author'], self._characters)}] {kind} in {self._where(ch, comment['thread_id'])}: {comment['body']}"
        for line in lc.question_lines(comment.get("structured", {}).get("questions") or []):
            text += f"\n  {line}"
        return self.situation(ch) + "\n" + text

    def _skill_due(self, ch: dict) -> str:
        """Spec §5.3: the injected skill rides a message whenever the one due for this character's position and the
        story's phase differs from what it was last told — not from the action that moved the phase, since an inbox
        item can be popped after the Proceed that preceded it. A position or a phase that carries none gets none.
        Updates skill_seen; the caller saves."""
        phase = self._stories[ch["story_key"]].phase
        name = skills.skill_name(ch.get("position", ""), phase)
        if not name or ch.get("skill_seen") == name:
            return ""
        ch["skill_seen"] = name                     # before the read: a missing file notifies once, not every delivery
        body = skills.skill_body(name)
        if not body and self.notifier is not None:
            self.notifier.error(f"no {name} skill under {skills.skills_dir()} — {ch['name']} runs without it")
        return body

    def _push(self, ch: dict, ctx, comment: dict):
        """One delivery to a live context: the situation line, the comment, and the skill for its position when new."""
        text = self._format(ch, comment)
        skill = self._skill_due(ch)
        ctx.send(text + (f"\n\n{skill}" if skill else ""))
        self._save_characters()

    def _deliver_to(self, ch: dict, comment: dict):
        """Spec §2.3 delivery: mid-turn, the attended thread is pushed now and everything else waits in the inbox;
        a waiting or idle character is woken by whatever arrives and attends its thread."""
        if self._stories[ch["story_key"]].phase in lc.TERMINAL:
            return  # retired
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        if ctx is None:
            return
        if ctx.status in WORKING and ch.get("attention") != comment["thread_id"]:
            ch.setdefault("inbox", []).append(comment["id"])
            self._save_characters()
            self._refresh()
            return
        ch["attention"] = comment["thread_id"]
        self._save_characters()
        self._push(ch, ctx, comment)

    def _route(self, key: str, comment: dict):
        for cid in self.addressees(key, comment):
            self._deliver_to(self._characters[cid], comment)

    # ---------------------------------------------------------------- turn end (spec §2.3)
    def _character_by_context(self, context_id: str) -> dict | None:
        return next((ch for ch in self._characters.values() if ch.get("live_context") == context_id), None)

    def _thread_anywhere(self, thread_id: str):
        for key, s in self._stories.items():
            for t in s.threads:
                if t.id == thread_id:
                    return key, t
        return None, None

    def _on_turn_end(self, context_id: str):
        """A character's turn ended (normal end, crash, or Stop): attention clears once its thread no longer waits on
        the cast; a character that awaits nothing has every owed thread yielded for it; then one inbox item."""
        ch = self._character_by_context(context_id)
        if ch is None:
            return
        ctx = self._contexts.get(context_id)
        if ctx is not None and getattr(ctx, "proc_cwd", None) not in (None, self._placement(ctx)[0]):
            ctx.recycle()   # its environment changed this turn: the next turn spawns there (§4.5)
        key = ch["story_key"]
        s = self._stories[key]
        if s.phase in lc.TERMINAL:
            self._sweep_environments(key)   # §4.8: a done story's worktrees go once nobody is still finishing a turn there
            return  # retired
        if ch.get("recast_pending") is not None:  # a recast waited for this boundary
            pending = ch.pop("recast_pending")
            self._recast_now(ch, pending.get("model", ""), pending.get("effort", ""), pending.get("preset", ""),
                             pending.get("cause", ""))
            return
        if not self.awaits(ch):
            status = getattr(ctx, "status", "idle")
            why = {"failed": "crashed", "stopped": "was stopped"}.get(status, "went quiet")
            text = ((ctx.last_assistant_text() if ctx is not None else "") or (getattr(ctx, "lastError", "") if ctx is not None else "")
                    or "(no output)")
            for t in lc.owes(s, ch["id"]):
                c = self._apply(key, lc.Yield(thread_id=t.id, by="system", kind="handoff",
                                              body=f"{ch['name']} {why}: {text}", auto_for=ch["id"]))
                self._route(key, c)
        _, att = self._thread_anywhere(ch.get("attention") or "")
        if att is None or att.turn != "cast":
            ch["attention"] = None  # it yielded or resolved there (itself, or the harness for it), or the thread closed
        inbox = ch.setdefault("inbox", [])
        while inbox:
            comment = self._comment_by_id(inbox.pop(0))
            if comment is not None:
                ch["attention"] = comment["thread_id"]
                self._save_characters()
                if ctx is not None:
                    self._push(ch, ctx, comment)
                break
        self._save_characters()
        self._refresh()

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

    @Slot(str, result=str)
    @Slot(str, str, result=str)
    @Slot(str, str, str, result=str)
    @Slot(str, str, str, str, result=str)
    @Slot(str, str, str, str, str, result=str)
    @intent
    def start(self, key, note="", model="", effort="", preset=""):
        return self._start(key, note, model, effort, preset)

    def _start(self, key, note="", model="", effort="", preset=""):
        key = self._key(key)
        position = getattr(cfg, "DEFAULT_POSITION", "protagonist")
        cast = self._casting.resolve(position, model, effort, preset)
        chr_id, thread_id = new_id("chr_"), new_id("thr_")
        prev_story, prev_comments = self._stories[key], list(self._comments.get(key, []))
        self._apply(key, lc.Start(thread_id=thread_id, protagonist=chr_id, note=note),
                    extra={"position": position, "model": cast["model"], "effort": cast["effort"], "preset": cast["preset"]})
        try:
            self._cast(key, cast, chr_id=chr_id, thread_id=thread_id, author="human", note=note)
        except Exception:
            # Don't leave the story wedged in planning with a protagonist that has no context.
            self._stories[key], self._comments[key] = prev_story, prev_comments
            self._save_story(key)
            self._refresh()
            raise
        self._refresh()
        return chr_id

    def _cast(self, key: str, cast: dict, *, thread_id: str, author: str, note: str, name: str = "",
              fork_from: str | None = None, chr_id: str | None = None, environment: str | None = None) -> dict:
        """Cast a character on `key` to lead `thread_id` (spec §2.1 Open a thread, §2.2 call): a record, a live
        context (fresh from the cast, or forked from `fork_from`'s live context), and its first message.
        `cast` is what CastStore.resolve made of a position and the three picks."""
        provider = cast.get("provider", "claude-code")
        if provider != "claude-code":
            raise ValueError(f"model {cast['model']!r} runs on provider {provider!r}, which is not implemented yet")
        taken = {ch["name"] for ch in self._characters.values() if ch["story_key"] == key}
        base = name or cast["label"]                 # no role to name it after: the position's label (spec §1)
        name, n = base, 2
        while name in taken:
            name, n = f"{base}-{n}", n + 1
        chr_id = chr_id or new_id("chr_")
        ch = {"id": chr_id, "story_key": key, "position": cast["position"], "model": cast["model"],
              "effort": cast["effort"], "preset": cast["preset"], "name": name, "live_context": None,
              "forked_from": fork_from, "attention": thread_id, "inbox": [], "recaps": [], "verbs_log": [],
              "environment": environment}
        self._characters[chr_id] = ch
        s = self._stories[key]
        env = {"HARNESS_CHARACTER_ID": chr_id}
        title = f"{key} · {name}"
        try:
            if fork_from is None:
                cid = self._contexts.create(cast["position"], model=cast["model"], effort=cast["effort"],
                                            preset=cast["preset"], story_key=key, owner=chr_id, title=title, env=env)
                first = render_brief(s, self._comments[key], self._characters, note, substories=self._substories(key),
                                     skill=self._skill_due(ch))
            else:
                src = self._characters[fork_from]
                src_ctx = self._contexts.get(src["live_context"]) if src.get("live_context") else None
                if src_ctx is None or src_ctx.status in WORKING or not getattr(src_ctx, "sessionId", ""):
                    raise lc.Rejected(f"{src['name']} is working or has never run; fork it when it stops")
                cid = self._contexts.fork(src["live_context"], position=cast["position"], model=cast["model"],
                                          effort=cast["effort"], preset=cast["preset"], owner=chr_id, story_key=key,
                                          title=title, env=env)
                # The conversation it inherits holds its source's skill, which is the wrong one the moment the
                # fork changed position — a fork of the protagonist is a friend now (spec §5.3).
                first = getattr(cfg, "FORK_NOTE", "").format(name=name, source=src["name"]) + note
                skill = self._skill_due(ch)
                if skill:
                    first += f"\n\n{skill}"
        except Exception:
            del self._characters[chr_id]
            raise
        ch["live_context"] = cid
        self._save_characters()
        self._contexts.get(cid).send(first)
        return ch

    def system_prompt(self, ctx) -> str | None:
        """Spec §5.3: the stable prompt of the character that owns `ctx`, built now from config, its cast and the
        skill files; None for contexts no character owns (bare contexts and asides keep their stored prompts)."""
        ch = self._characters.get(ctx.meta.get("owner") or "")
        if ch is None or ch["story_key"] not in self._stories:
            return None
        return self._character_prompt(self._stories[ch["story_key"]], ch, self._cast_of(ch))

    def _cast_of(self, ch: dict) -> dict:
        """The cast a character was cast with, resolved fresh from its position and its three picks."""
        try:   # rebuild, not resolve: a pick that no longer stands falls back to the position's own, and
               # never costs the character the instructions or the outline rule the position carries (§1).
            return self._casting.rebuild(ch.get("position", ""), ch.get("model", ""), ch.get("effort", ""), ch.get("preset", ""))
        except (ValueError, KeyError):
            return {}

    def _character_prompt(self, s: lc.Story, ch: dict, cast: dict) -> str:
        rule = getattr(cfg, "OUTLINE_RULE_REQUIRED", "") if cast.get("outline_first") else getattr(cfg, "OUTLINE_RULE_OPTIONAL", "")
        instructions = (cast.get("instructions") or "").strip()
        position = f"Position: {cast.get('label') or ch.get('position', '')}." + (f" {instructions}" if instructions else "") + f"\n{rule}"
        return getattr(cfg, "CHARACTER_SYSTEM_PROMPT", "").format(
            name=ch["name"], character_id=ch["id"], story_key=s.key, title=s.title,
            meta_skill=skills.skill_body("being-a-character"), position=position)

    def _author_action(self, key, action, *, resume: bool):
        key = self._key(key)
        comment = self._apply(key, action)
        if resume:
            self._route(key, comment)
        owner = self._characters.get(self._stories[key].author)
        if owner is not None and comment["author"] == owner["id"] and getattr(action, "by", None) == owner["id"]:
            if resume or comment["kind"] == "system":  # the human acted for the owner (§2.3): the owner is told
                self._deliver_to(owner, comment)
        return comment

    def _approve(self, key: str, by: str, note: str) -> dict:
        """§2.1 Approve in the store's order (workspace spec §4.8): the lifecycle precondition, every environment
        prechecked, each fast-forwarded, then the reducer's comment carrying what landed, then the sweep. A story is
        never done with unmerged work; a failure partway leaves the story implementing and the retry finishes."""
        lc.step(self._stories[key], lc.Approve(by=by, note=note), comment_id="probe", now=0.0)   # rejection only: pure
        recs = self.environments.records(key)
        behind = []
        for r in recs:
            n = self.environments.behind(r)
            if n:
                tgt = self.environments.describe(r)["target"]
                behind.append(f"{r['branch']} is {n} commit{'' if n == 1 else 's'} behind {tgt} in {r['repo']}")
        if behind:
            raise lc.Rejected("cannot approve: " + "; ".join(behind) + " — reply and have the cast rebase, then approve again")
        merged = [self.environments.integrate(r) for r in recs]
        c = self._author_action(key, lc.Approve(by=by, note=note, merged=merged), resume=False)
        self._sweep_environments(key)
        return c

    def _sweep_environments(self, key: str) -> None:
        """Workspace spec §4.8 cleanup: once a done story has no character mid-turn, its worktrees are removed.
        Every settled context of the cast is recycled first: an idle agent process still stands in the worktree it
        was spawned in, and a directory pulled out from under it strands the next turn — on Windows it also makes
        `worktree remove` fail. A failed remove leaves the record live; the next turn end, or the next load, retries."""
        if self._stories[key].phase != "done":
            return
        settled = []
        for ch in self._characters.values():
            if ch["story_key"] == key and ch.get("live_context"):
                ctx = self._contexts.get(ch["live_context"])
                if ctx is not None:
                    if ctx.status in WORKING:
                        return
                    settled.append(ctx)
        recs = self.environments.records(key)
        if not recs:
            return
        for ctx in settled:
            ctx.recycle()   # drops the idle process; the next send spawns a fresh one where §4.5 puts it
        for rec in recs:
            try:
                self.environments.remove(rec)
            except EnvError as e:
                if self.notifier is not None:
                    self.notifier.error(f"{key}: {e}")
        self._refresh()

    def _on_behalf(self, key: str) -> str:
        """Who a human action on `key` is by: the story's author — a character for its sub-stories (§2.3)."""
        return self._stories[self._key(key)].author

    def _substories(self, key: str) -> list[dict]:
        return [{"key": x.key, "title": x.title, "phase": x.phase, "ball": x.ball or ""}
                for x in self._stories.values() if x.parent_story == key]

    def _stop_cast(self, key: str):
        for ch in self._characters.values():
            if ch["story_key"] == key and ch.get("live_context"):
                ctx = self._contexts.get(ch["live_context"])
                if ctx is not None:
                    ctx.stop()

    @Slot(str, str)
    @intent
    def proceed(self, key, note=""):
        self._author_action(key, lc.Proceed(by=self._on_behalf(key), note=note), resume=True)

    @Slot(str, str)
    @intent
    def approve(self, key, note=""):
        self._approve(self._key(key), self._on_behalf(key), note)

    @Slot(str, str)
    @intent
    def backToPlanning(self, key, note=""):
        self._author_action(key, lc.BackToPlanning(by=self._on_behalf(key), note=note), resume=True)

    @Slot(str, str)
    @intent
    def cancel(self, key, note=""):
        key = self._key(key)
        self._author_action(key, lc.Cancel(by=self._on_behalf(key), note=note), resume=False)
        self._stop_cast(key)
        for sub in [k for k, x in self._stories.items() if x.parent_story == key and x.phase not in lc.TERMINAL]:
            self.cancel(sub)
        self._refresh()

    @Slot(str)
    @Slot(str, str)
    @Slot(str, str, str)
    @Slot(str, str, str, str)
    @Slot(str, str, str, str, str)
    @intent
    def reopen(self, key, note="", model="", effort="", preset=""):
        """Reopen resumes the protagonist (§2.1). With a model/effort/preset it recasts instead: the story
        reopens, the protagonist gets a fresh memory, and the note is delivered to that."""
        if not model and not effort and not preset:
            self._author_action(key, lc.Reopen(by=self._on_behalf(key), note=note), resume=True)
            return
        key = self._key(key)
        action = lc.Reopen(by=self._on_behalf(key), note=note)
        comment = self._apply(key, action)
        self._recast_now(self._characters[self._stories[key].protagonist], model, effort, preset)
        self._route(key, comment)   # _author_action(resume=True), with the recast in between
        owner = self._characters.get(self._stories[key].author)
        if owner is not None and comment["author"] == owner["id"] and action.by == owner["id"]:
            self._deliver_to(owner, comment)

    @Slot(str, str, result="QVariantMap")
    @Slot(str, str, str, result="QVariantMap")
    @intent
    def resolve(self, key, thread_id, note=""):
        """Close a side thread waiting on the author: nobody is resumed or notified (§2.1)."""
        key = self._key(key)
        comment = self._author_action(key, lc.Resolve(thread_id=thread_id, by=self._on_behalf(key), note=note), resume=False)
        self._clear_attention(key, thread_id)
        return comment

    @Slot(str, str, result=str)
    @intent
    def openThread(self, key, body):
        """Spec §2.1 Open a thread: plain → protagonist; "@Name …" → Name; "/call <Name> [note]" → a fresh friend
        of that name; "/fork @Name [note]" → a friend forked from Name. Returns the thread id."""
        key = self._key(key)
        s = self._stories[key]
        body = (body or "").strip()
        thread_id = new_id("thr_")
        m_call = re.match(r"/call\s+(\S+)\s*(.*)", body, re.S)
        m_fork = re.match(r"/fork\s+@([\w-]+)\s*(.*)", body, re.S)
        m_name = re.match(r"@([\w-]+)\b", body)
        if m_call or m_fork:
            friend_name = ""
            if m_call:
                friend_name = m_call.group(1)
                cast = self._casting.resolve(FRIEND_POSITION)
                note, fork_from, environment = m_call.group(2).strip() or f"called in as {friend_name}", None, None
            else:
                source = self._by_name(key, m_fork.group(1))    # a fork is cast exactly as its source was
                cast = self._casting.resolve(source["position"], source.get("model", ""), source.get("effort", ""),
                                             source.get("preset", ""))
                note, fork_from, environment = m_fork.group(2).strip() or "a side question", source["id"], source.get("environment")
            chr_id = new_id("chr_")
            prev_story, prev_comments = self._stories[key], list(self._comments.get(key, []))
            self._apply(key, lc.OpenThread(thread_id=thread_id, author="human", lead=chr_id, body=note))
            try:
                self._cast(key, cast, chr_id=chr_id, thread_id=thread_id, author="human", note=note, name=friend_name,
                           fork_from=fork_from, environment=environment)
            except Exception:
                self._stories[key], self._comments[key] = prev_story, prev_comments
                self._save_story(key)
                self._refresh()
                raise
            self._refresh()
            return thread_id
        lead = self._by_name(key, m_name.group(1))["id"] if m_name else s.protagonist
        comment = self._apply(key, lc.OpenThread(thread_id=thread_id, author="human", lead=lead, body=body))
        self._route(key, comment)
        return thread_id

    # ---------------------------------------------------------------- recast (spec §2.1, §3.4)
    @Slot(str, str, result=str)
    @Slot(str, str, str, result=str)
    @Slot(str, str, str, str, result=str)
    @Slot(str, str, str, str, str, result=str)
    @intent
    def recast(self, key, character_id, model="", effort="", preset=""):
        """Replace a character's live context — same character, fresh memory — at its next turn boundary.
        Returns the new context id, or "" when deferred until the current turn ends."""
        key = self._key(key)
        ch = self._characters[character_id]
        if ch["story_key"] != key:
            raise lc.Rejected(f"{ch['name']} is not on {key}")
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        if ctx is not None and ctx.status in WORKING:
            ch["recast_pending"] = {"model": model, "effort": effort, "preset": preset}
            self._save_characters()
            return ""
        return self._recast_now(ch, model, effort, preset)

    def _recast_now(self, ch: dict, model: str = "", effort: str = "", preset: str = "", cause: str = "") -> str:
        key = ch["story_key"]
        s = self._stories[key]
        cast = self._casting.resolve(ch["position"], model or ch.get("model", ""), effort or ch.get("effort", ""),
                                     preset or ch.get("preset", ""))
        old_id = ch.get("live_context")
        old = self._contexts.get(old_id) if old_id else None
        recap = self._comment_by_id(ch["recaps"][-1]) if ch.get("recaps") else None
        fresh = (recap is not None and old is not None
                 and getattr(old, "turns", 0) - ch.get("recap_turns", 0) <= getattr(cfg, "RECAP_STALE_TURNS", 20))
        rung = "rung 1: fresh recap" if fresh else "rung 3: no fresh recap"
        ch["model"], ch["effort"], ch["preset"] = cast["model"], cast["effort"], cast["preset"]
        ch["skill_seen"] = None                     # a fresh context: the brief ends with the skill for its position
        skill = self._skill_due(ch)
        situation = (f"you are a recast of {ch['name']}; your predecessor's recap is above. "
                     f"You were attending #{lc.thread_label(s, ch.get('attention') or s.main_thread)}; {len(ch.get('inbox', []))} items wait in your inbox; "
                     f"you await {self._awaits_line(ch)} and owe {self._owes_line(ch)}.")
        cid = self._contexts.create(cast["position"], model=cast["model"], effort=cast["effort"], preset=cast["preset"],
                                    story_key=key, owner=ch["id"], title=f"{key} · {ch['name']}",
                                    env={"HARNESS_CHARACTER_ID": ch["id"]}, predecessor=old_id)
        ch["live_context"] = cid
        ch.pop("recast_pending", None)
        ch.pop("context_warned", None)              # the crossings belong to the context that is gone (§3.4)
        ch.pop("context_maxed", None)
        self._save_characters()
        if old is not None:
            old.stop()
        self._apply(key, lc.Note(thread_id=s.main_thread,
                                 body=f"recast {ch['name']} as {cast['label']} on {cast['model'] or 'the cli default'} "
                                      f"({'context; ' if cause == 'context' else ''}{rung})"))
        self._contexts.get(cid).send(render_brief(s, self._comments[key], self._characters, "",
                                                  substories=self._substories(key), situation=situation, skill=skill))
        self._refresh()
        return cid

    # ---------------------------------------------------------------- asides (spec §3.5)
    def _aside_for(self, comment_id: str) -> str:
        for ctx in self._contexts.all():
            about = ctx.meta.get("about") or {}
            if about.get("comment_id") == comment_id:
                return ctx.id
        return ""

    def aside_source(self, key: str, comment: dict) -> str:
        """The context an aside on `comment` would fork, or "" when the button is disabled: only the memory
        that wrote the comment (never a recast successor), and only while it is resumable and not mid-turn."""
        cid = comment.get("context") if comment["author"] in self._characters else None
        ctx = self._contexts.get(cid) if cid else None
        if ctx is None or not getattr(ctx, "sessionId", "") or ctx.status in ("starting", "working"):
            return ""
        return cid

    @Slot(str, str, result=str)
    @intent
    def aside(self, key, comment_id):
        """Open (or reopen) the aside on a character's comment: a private bare context forked from the memory
        that wrote it. Nothing about it enters the story record."""
        key = self._key(key)
        existing = self._aside_for(comment_id)
        if existing:
            return existing
        comment = next((c for c in self._comments.get(key, []) if c["id"] == comment_id), None)
        if comment is None:
            raise KeyError(comment_id)
        ch = self._characters.get(comment["author"])
        if ch is None:
            raise lc.Rejected("asides are for characters' comments")
        source = self.aside_source(key, comment)
        if not source:
            raise lc.Rejected(f"{ch['name']} is working or its memory is gone; try again when it stops")
        s = self._stories[key]
        n = next((i + 1 for i, t in enumerate(s.threads) if t.id == comment["thread_id"]), 0)
        quoted = "\n> ".join(comment["body"].splitlines()) or "(empty)"
        prompt = getattr(cfg, "ASIDE_SYSTEM_PROMPT", "").format(name=ch["name"], story_key=key, thread_id=n, body=quoted)
        cid = self._contexts.fork(source, position=getattr(cfg, "DEFAULT_BARE_POSITION", "bare"), owner="human",
                                  title=f"aside on #{n} · {ch['name']}", system_prompt=prompt,
                                  about={"story_key": key, "comment_id": comment_id})
        self._refresh()
        return cid

    @Slot(str, str, result="QVariantMap")
    @Slot(str, str, str, result="QVariantMap")
    @intent
    def comment(self, key, body, thread_id=""):
        key = self._key(key)
        s = self._stories[key]
        tid = thread_id or s.main_thread or ""
        return self._author_action(key, lc.Comment(thread_id=tid, by=self._on_behalf(key), body=body), resume=True)

    @Slot(str, str, "QVariantList", str, result="QVariantMap")
    @intent
    def answer(self, key, thread_id, answers, text):
        """The story view's reply to a question (spec §4): the picks by question index as `N. <pick>` lines, then the
        composer text, in one comment that carries the picks as `answers`."""
        key = self._key(key)
        s = self._stories[key]
        tid = thread_id or s.main_thread or ""
        picks = [str(a or "").strip() for a in answers]
        lines = [f"{i + 1}. {a}" for i, a in enumerate(picks) if a]
        if text.strip():
            lines.append(text.strip())
        if not lines:
            raise lc.Rejected("nothing to say: pick an option or write a reply")
        return self._author_action(key, lc.Comment(thread_id=tid, by=self._on_behalf(key), body="\n".join(lines),
                                                   answers=picks if any(picks) else []), resume=True)

    # ---------------------------------------------------------------- cast verbs (via IPC)
    def _char(self, character_id: str) -> tuple[str, dict]:
        ch = self._characters[character_id]  # KeyError for unknown characters
        return ch["story_key"], ch

    def _tid(self, key: str, ch: dict, thread_id: str = "") -> str:
        """A verb's thread: the one named, else the attended one, else main; `main` names the main thread."""
        s = self._stories[key]
        tid = thread_id or ch.get("attention") or s.main_thread
        return s.main_thread if tid == "main" else tid

    def cast_yield(self, character_id, kind, body, questions=(), thread_id="", checks=()) -> dict:
        key, ch = self._char(character_id)
        tid = self._tid(key, ch, thread_id)
        open_subs = self._row(key)["openSubstories"] if tid == self._stories[key].main_thread else 0
        c = self._apply(key, lc.Yield(thread_id=tid, by=character_id, kind=kind, body=body, questions=[dict(q) for q in questions],
                                      checks=[dict(c) for c in checks], open_substories=open_subs))
        self._route(key, c)
        return c

    def cast_create(self, character_id, title, description="", start=False, model="", effort="", preset="") -> str:
        """Spec §2.2 create: a sub-story authored by the character, under its story."""
        parent, ch = self._char(character_id)
        key = self.workspace.next_key()
        self._stories[key] = lc.Story(key=key, title=title, description=description, phase="todo",
                                      author=character_id, parent_story=parent)
        self._created[key] = time.time()
        self._comments[key] = []
        self.workspace.story_dir(key)
        self._save_story(key)
        if start:
            self._start(key, "", model, effort, preset)
        self._refresh()
        return key

    def cast_author(self, character_id, verb, key, **kw) -> dict:
        """Spec §2.2: the §2.1 author actions on a story the character authored (its sub-stories)."""
        key = self._key(key)
        s = self._stories[key]
        if s.author != character_id:
            raise lc.Rejected(f"only the author of {key} ({author_name(s.author, self._characters)}) can {verb} it")
        by, note = character_id, kw.get("note", "")
        if verb == "reply":
            tid = kw.get("thread_id") or s.main_thread
            return self._author_action(key, lc.Comment(thread_id=tid, by=by, body=kw["body"]), resume=True)
        if verb == "resolve":
            c = self._author_action(key, lc.Resolve(thread_id=kw["thread_id"], by=by, note=note), resume=False)
            self._clear_attention(key, kw["thread_id"])
            return c
        if verb == "recast":
            return {"context": self.recast(key, kw["character"], kw.get("model", ""), kw.get("effort", ""),
                                           kw.get("preset", ""))}
        if verb == "approve":
            c = self._approve(key, by, note)
            self._refresh()
            return c
        actions = {"proceed": lc.Proceed(by=by, note=note),
                   "cancel": lc.Cancel(by=by, note=note), "reopen": lc.Reopen(by=by, note=note),
                   "back": lc.BackToPlanning(by=by, note=note)}
        if verb not in actions:
            raise lc.Rejected(f"unknown author verb {verb!r}")
        c = self._author_action(key, actions[verb], resume=True)
        if verb == "cancel":
            self._stop_cast(key)
            for sub in [k for k, x in self._stories.items() if x.parent_story == key and x.phase not in lc.TERMINAL]:
                self.cast_author(character_id if self._stories[sub].author == character_id else self._stories[sub].author, "cancel", sub)
        self._refresh()
        return c

    def cast_call(self, character_id, note, as_name="", fork=False, model="", effort="", preset="") -> dict:
        """Spec §2.2 call: a friend on its own thread, authored by the caller; --fork copies the caller's memory.
        Nobody picks the position — a call casts a friend; --as names it, and it is the position's label otherwise."""
        key, ch = self._char(character_id)
        if self._stories[key].phase in lc.TERMINAL:
            raise lc.Rejected(f"{key} is terminal")
        cast = self._casting.resolve(FRIEND_POSITION, model, effort, preset)
        if not note:
            raise lc.Rejected("call needs a --note: the friend's call-in note is the root of its thread")
        chr_id, thread_id = new_id("chr_"), new_id("thr_")
        prev_story, prev_comments = self._stories[key], list(self._comments.get(key, []))
        self._apply(key, lc.OpenThread(thread_id=thread_id, author=character_id, lead=chr_id, body=note))
        try:
            friend = self._cast(key, cast, chr_id=chr_id, thread_id=thread_id, author=character_id, note=note,
                                name=as_name, fork_from=character_id if fork else None, environment=ch.get("environment"))
        except Exception:
            self._stories[key], self._comments[key] = prev_story, prev_comments
            self._save_story(key)
            self._refresh()
            raise
        self._refresh()
        return {"thread": thread_id, "character": friend["id"], "name": friend["name"]}

    def cast_wait(self, character_id) -> dict:
        """Spec §2.2 wait: a guard, not a block — what the caller awaits, or why it must not stop."""
        key, ch = self._char(character_id)
        awaits = self.awaits(ch)
        if not awaits:
            if self.owes(ch):   # the one state where stopping is wrong: the turn would end in silence
                raise lc.Rejected(f"you await nothing and owe {self._owes_line(ch)} — yield instead")
            return {"awaits": [], "message": "you await nothing and owe nothing — end your turn; a reply will wake you"}
        s = self._stories[key]
        rows = []
        for item in awaits:
            t = next((t for t in s.threads if t.id == item), None)
            rows.append({"thread": item, "lead": author_name(t.lead, self._characters)} if t else {"story": item})
        return {"awaits": rows, "message": "end your turn now; you will be woken when any of these yields to you"}

    # ---------------------------------------------------------------- repos and environments (workspace spec §3.2, §4)
    def cast_repo_add(self, character_id, spec, name="", checks="", setup="", base="") -> dict:
        key, ch = self._char(character_id)
        rec = register_repo(self.workspace, spec, name=name, checks=checks, setup=setup, base=base)
        tid = ch.get("attention") or self._stories[key].main_thread
        self._apply(key, lc.Note(thread_id=tid, body=f"Registered repo `{rec['name']}` at `{rec['path']}`"))
        self._refresh()
        return rec

    def repo_list(self) -> list[dict]:
        return [{**r, "status": self.workspace.repo_status(r["name"])} for r in self.workspace.repos]

    def cast_env_open(self, character_id, repo) -> dict:
        key, ch = self._char(character_id)
        if not repo:
            raise EnvError("env open needs a repo name; `repo list` shows what is registered")
        d = self.environments.open(key, repo)
        ch["environment"] = repo
        self._save_characters()
        s = self._stories[key]
        if repo not in s.repos:
            s.repos.append(repo)
            self._save_story(key)
        self._refresh()
        return d

    def cast_env_list(self, character_id) -> list[dict]:
        key, _ = self._char(character_id)
        return [self.environments.describe(r) for r in self.environments.records(key)]

    def env_checks(self, character_id, thread_id="") -> dict:
        """§4.6: what the CLI must gate on before posting a handoff — only on the main thread of an implementing story.
        Every environment of the story: the tree gate covers them all, `checks` runs where a repo has them."""
        key, ch = self._char(character_id)
        s = self._stories[key]
        tid = self._tid(key, ch, thread_id)
        run = s.phase == "implementing" and tid == s.main_thread
        envs = self.cast_env_list(character_id) if run else []
        return {"run": run, "environments": envs, "policy": getattr(cfg, "HANDOFF_CHECKS", "gate"),
                "limit": getattr(cfg, "CHECKS_OUTPUT_LIMIT", 4000), "timeout": getattr(cfg, "CHECKS_TIMEOUT_S", 1800)}

    def cast_inbox(self, character_id) -> list[dict]:
        key, ch = self._char(character_id)
        return [dict(c) for i in ch.get("inbox", []) if (c := self._comment_by_id(i)) is not None]

    @Slot(str, str, result="QVariantMap")
    @intent
    def speak(self, character_id, text):
        """Spec §2.3: typing in a character's context view is a human comment in its attended thread — the
        same channel, a different skin; a root thread to it when it attends nothing."""
        key, ch = self._char(character_id)
        if ch.get("attention"):
            skey, _ = self._thread_anywhere(ch["attention"])
            if skey is not None:
                return self._author_action(skey, lc.Comment(thread_id=ch["attention"], by="human", body=text), resume=True)
        tid = new_id("thr_")
        c = self._apply(key, lc.OpenThread(thread_id=tid, author="human", lead=character_id, body=text))
        self._route(key, c)
        return c

    def cast_proceed(self, character_id, note="") -> dict:
        key, ch = self._char(character_id)
        if self._cast_of(ch).get("outline_first"):  # an outline approved since the most recent entry into planning (§2.2)
            comments = self._comments.get(key, [])
            last_planning = max((i for i, c in enumerate(comments)
                                 if (c.get("structured", {}).get("transition") or {}).get("to", [None])[0] == "planning"), default=-1)
            approved = {"from": ["planning", "author"], "to": ["implementing", "cast"]}
            if not any(c.get("structured", {}).get("transition") == approved for c in comments[last_planning + 1:]):
                raise lc.Rejected("your position requires an approved outline first: `yield --handoff` the outline and wait for Proceed")
        c = self._apply(key, lc.Proceed(by=character_id, note=note))
        ch["skill_seen"] = "implementing-a-story"   # goes out on stdout (§2.2); the next delivery must not repeat it
        self._save_characters()
        return {**c, "skill": skills.skill_body("implementing-a-story")}

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

    def cast_recap(self, character_id, body, thread_id="") -> dict:
        key, ch = self._char(character_id)
        tid = self._tid(key, ch, thread_id)
        c = self._apply(key, lc.Recap(by=character_id, body=body, thread_id=tid))
        ch.setdefault("recaps", []).append(c["id"])
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        ch["recap_turns"] = getattr(ctx, "turns", 0) if ctx is not None else 0
        self._save_characters()
        self._refresh()   # `_apply` already refreshed, but before the recap counted: `recap due` clears now
        return c

    def cast_comment(self, character_id, body, thread_id="", to=()) -> dict:
        key, ch = self._char(character_id)
        mentions = " ".join(m if m.startswith("@") else "@" + m for m in to)
        if not thread_id and to:
            lead = self._by_name(key, mentions.split()[0].lstrip("@"))["id"]
            tid = new_id("thr_")
            c = self._apply(key, lc.OpenThread(thread_id=tid, author=character_id, lead=lead, body=body))
        else:
            tid = self._tid(key, ch, thread_id)
            c = self._apply(key, lc.Comment(thread_id=tid, by=character_id, body=body + (" " + mentions if mentions else "")))
        self._route(key, c)
        return c

    def log_verb(self, character_id, verb, args: dict, ok: bool, error: str = ""):
        ch = self._characters.get(character_id)
        if ch is None:
            return
        log = ch.setdefault("verbs_log", [])
        log.append({"verb": verb, "args": dict(args), "ok": ok, "error": error, "ts": time.time()})
        if len(log) > VERBS_LOG_MAX:
            del log[:len(log) - VERBS_LOG_MAX]
        self._save_characters()
