"""The story state machine — lifecycle spec §1, §2, §2.4. Pure: no Qt, no I/O, no ids minted here.

    step(story, action, comment_id=..., now=...) -> (story', comment)

`story` is never mutated. Rejections raise `Rejected(reason)`; the CLI prints the reason.
Nobody sets status: phase and turns change only as side effects of the actions below."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field

PHASES = ("backlog", "todo", "planning", "implementing", "done", "canceled")
UNSTARTED = ("backlog", "todo")
ACTIVE = ("planning", "implementing")
TERMINAL = ("done", "canceled")
YIELD_KINDS = ("question", "handoff")


class Rejected(Exception):
    """The action is not allowed in this cell; str(e) is the reason."""


# ---------------------------------------------------------------- state

@dataclass
class Thread:
    id: str
    author: str                      # "human" | character id
    lead: str                        # character id
    turn: str = "cast"               # "cast" | "author" | "resolved"
    pending_yield: str | None = None  # comment id while turn == "author"


@dataclass
class Story:
    key: str
    title: str
    description: str = ""
    priority: str = "medium"
    phase: str = "backlog"
    author: str = "human"
    protagonist: str | None = None
    main_thread: str | None = None
    parent_story: str | None = None
    threads: list[Thread] = field(default_factory=list)

    @property
    def ball(self) -> str | None:
        m = self.main
        return m.turn if self.phase in ACTIVE and m is not None else None

    @property
    def main(self) -> Thread | None:
        return next((t for t in self.threads if t.id == self.main_thread), None) if self.main_thread else None

    def thread(self, thread_id: str) -> Thread:
        for t in self.threads:
            if t.id == thread_id:
                return t
        raise KeyError(thread_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Story":
        d = dict(d)
        d["threads"] = [Thread(**t) for t in d.get("threads", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------- actions

@dataclass
class Start:
    thread_id: str
    protagonist: str
    note: str = ""
    role: str = ""


@dataclass
class Reply:
    thread_id: str
    body: str
    by: str = "human"


@dataclass
class Resolve:
    thread_id: str
    by: str = "human"
    note: str = ""


@dataclass
class Proceed:
    by: str
    note: str = ""


@dataclass
class Approve:
    note: str = ""
    by: str = "human"


@dataclass
class BackToPlanning:
    note: str = ""
    by: str = "human"


@dataclass
class Cancel:
    note: str = ""
    by: str = "human"


@dataclass
class Reopen:
    note: str = ""
    by: str = "human"


@dataclass
class OpenThread:
    thread_id: str
    author: str
    lead: str
    body: str


@dataclass
class Yield:
    thread_id: str
    by: str
    kind: str
    body: str
    options: list[str] = field(default_factory=list)
    open_substories: int = 0
    checks: list[dict] = field(default_factory=list)


@dataclass
class Recap:
    by: str
    body: str


@dataclass
class Comment:
    thread_id: str
    by: str
    body: str


# ---------------------------------------------------------------- helpers

def _comment(story: Story, comment_id: str, now: float, *, thread_id: str | None, author: str, kind: str,
             body: str, reply_to: str | None = None, structured: dict | None = None) -> dict:
    return {"id": comment_id, "story_key": story.key, "thread_id": thread_id, "reply_to": reply_to,
            "author": author, "kind": kind, "body": body, "mentions": [], "structured": structured or {},
            "attachments": [], "context": None, "created_at": now}


def _cell(story: Story) -> list:
    return [story.phase, story.ball]


def _require_thread(story: Story, thread_id: str) -> Thread:
    try:
        return story.thread(thread_id)
    except KeyError:
        raise Rejected(f"no thread {thread_id!r} on {story.key}") from None


def _require_started_active(story: Story):
    if story.main_thread is None:
        raise Rejected(f"{story.key} has not been started")
    if story.phase in TERMINAL:
        raise Rejected(f"{story.key} is terminal ({story.phase})")


def _with_note(base: str, note: str) -> str:
    return f"{base} — {note}" if note else base


# ---------------------------------------------------------------- the machine

def step(story: Story, action, *, comment_id: str, now: float) -> tuple[Story, dict]:
    before = _cell(story)
    s = copy.deepcopy(story)

    if isinstance(action, Start):
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase}); Reopen it instead")
        if s.phase not in UNSTARTED:
            raise Rejected(f"{s.key} is already started ({s.phase})")
        s.threads.append(Thread(id=action.thread_id, author=s.author, lead=action.protagonist))
        s.main_thread, s.protagonist, s.phase = action.thread_id, action.protagonist, "planning"
        c = _comment(s, comment_id, now, thread_id=action.thread_id, author=s.author, kind="text",
                     body=action.note or "Started.")

    elif isinstance(action, OpenThread):
        _require_started_active(s)
        if any(t.id == action.thread_id for t in s.threads):
            raise Rejected(f"thread {action.thread_id!r} already exists")
        s.threads.append(Thread(id=action.thread_id, author=action.author, lead=action.lead))
        c = _comment(s, comment_id, now, thread_id=action.thread_id, author=action.author, kind="text", body=action.body)

    elif isinstance(action, Yield):
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase})")
        if action.kind not in YIELD_KINDS:
            raise Rejected(f"yield kind must be one of {YIELD_KINDS}, not {action.kind!r}")
        t = _require_thread(s, action.thread_id)
        if t.pending_yield is not None:
            raise Rejected(f"thread {t.id} already waits on its author")
        if t.id == s.main_thread and action.by != s.protagonist:
            raise Rejected("only the protagonist yields on the main thread")
        if action.by == t.author:
            raise Rejected("a thread's author cannot yield in it")
        if t.id == s.main_thread and s.phase == "implementing" and action.kind == "handoff" and action.open_substories:
            raise Rejected(f"{action.open_substories} sub-stor{'y is' if action.open_substories == 1 else 'ies are'} still open")
        t.turn, t.pending_yield = "author", comment_id
        structured: dict = {}
        if action.options:
            structured["options"] = list(action.options)
        if action.checks:
            structured["checks"] = list(action.checks)
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind=action.kind, body=action.body,
                     structured=structured)

    elif isinstance(action, Reply):
        t = _require_thread(s, action.thread_id)
        if t.turn != "author":
            raise Rejected(f"thread {t.id} is not waiting on its author")
        if action.by != t.author:
            raise Rejected(f"only the thread's author ({t.author}) can reply here")
        pending, t.turn, t.pending_yield = t.pending_yield, "cast", None
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind="text", body=action.body, reply_to=pending)

    elif isinstance(action, Resolve):
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase}); its threads are read-only until Reopen")
        t = _require_thread(s, action.thread_id)
        if t.id == s.main_thread:
            raise Rejected("the main thread is never resolved directly; Approve or Cancel the story")
        if action.by != t.author:
            raise Rejected(f"only the thread's author ({t.author}) can resolve it")
        if t.turn != "author":
            raise Rejected(f"thread {t.id} is not waiting on its author (turn: {t.turn}); "
                           "a request to the cast cannot be retracted, only its answer resolved")
        pending, t.turn, t.pending_yield = t.pending_yield, "resolved", None
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind="system",
                     body=_with_note("resolved", action.note), reply_to=pending)

    elif isinstance(action, Comment):
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase}); its threads are read-only until Reopen")
        t = _require_thread(s, action.thread_id)
        if t.turn == "author" and action.by == t.author:
            return step(story, Reply(thread_id=t.id, body=action.body, by=action.by), comment_id=comment_id, now=now)
        if t.turn == "resolved":
            t.turn = "cast"  # any comment reopens a resolved thread (§2.2 reopen rule)
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind="text", body=action.body)

    elif isinstance(action, Recap):
        if s.main_thread is None:
            raise Rejected(f"{s.key} has not been started")
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase}); its threads are read-only until Reopen")
        c = _comment(s, comment_id, now, thread_id=s.main_thread, author=action.by, kind="recap", body=action.body)

    elif isinstance(action, Proceed):
        if s.phase != "planning":
            raise Rejected(f"proceed is only allowed while planning ({s.key} is {s.phase})")
        m = s.main
        if action.by == s.author:
            if m.turn != "author":
                raise Rejected("the author can proceed only while the ball is theirs")
            body = _with_note("outline approved", action.note)
        elif action.by == s.protagonist:
            if m.turn != "cast":
                raise Rejected("the protagonist can proceed only while the ball is with the cast")
            body = _with_note("proceeding to implementing", action.note)
        else:
            raise Rejected("only the author or the protagonist can proceed")
        s.phase, m.turn, m.pending_yield = "implementing", "cast", None
        c = _comment(s, comment_id, now, thread_id=m.id, author=action.by, kind="system", body=body)

    elif isinstance(action, (Approve, BackToPlanning)):
        if action.by != s.author:
            raise Rejected(f"only the author ({s.author}) can do that")
        if (s.phase, s.ball) != ("implementing", "author"):
            raise Rejected(f"requires (implementing, author); {s.key} is ({s.phase}, {s.ball})")
        m = s.main
        if isinstance(action, Approve):
            for t in s.threads:  # terminal sweep: every open thread resolves, main included
                t.turn, t.pending_yield = "resolved", None
            s.phase, body = "done", _with_note("approved", action.note)
        else:
            m.turn, m.pending_yield = "cast", None
            s.phase, body = "planning", _with_note("back to planning", action.note)
        c = _comment(s, comment_id, now, thread_id=m.id, author=action.by, kind="system", body=body)

    elif isinstance(action, Cancel):
        if action.by != s.author:
            raise Rejected(f"only the author ({s.author}) can cancel")
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is already terminal ({s.phase})")
        s.phase = "canceled"
        for t in s.threads:  # terminal sweep: every open thread resolves, main included
            t.turn, t.pending_yield = "resolved", None
        c = _comment(s, comment_id, now, thread_id=s.main_thread, author=action.by, kind="system",
                     body=_with_note("canceled", action.note))

    elif isinstance(action, Reopen):
        if action.by != s.author:
            raise Rejected(f"only the author ({s.author}) can reopen")
        if s.phase not in TERMINAL:
            raise Rejected(f"reopen requires a terminal story; {s.key} is {s.phase}")
        if s.main is None:
            s.phase = "todo"
            body = _with_note("reopened (never started) — back to todo", action.note)
        else:
            s.phase = "implementing"
            s.main.turn, s.main.pending_yield = "cast", None
            body = _with_note("reopened", action.note)
        c = _comment(s, comment_id, now, thread_id=s.main_thread, author=action.by, kind="system", body=body)

    else:
        raise Rejected(f"unknown action {type(action).__name__}")

    after = _cell(s)
    if after != before:
        c["structured"]["transition"] = {"from": before, "to": after}
    return s, c


# ---------------------------------------------------------------- invariants (§2.4)

def check_invariants(story: Story) -> None:
    assert story.phase in PHASES, f"bad phase {story.phase!r}"
    if story.phase in ACTIVE:
        assert story.main is not None and story.protagonist, "active story without main thread/protagonist"
    if story.main_thread is not None:
        assert story.main is not None, "main_thread points at no thread"
        assert story.main.lead == story.protagonist, "main thread lead must be the protagonist"
        assert story.main.author == story.author, "main thread author must be the story author"
    ids = [t.id for t in story.threads]
    assert len(ids) == len(set(ids)), "duplicate thread ids"
    for t in story.threads:
        assert t.turn in ("cast", "author", "resolved"), f"bad turn {t.turn!r}"
        assert (t.turn == "author") == (t.pending_yield is not None), f"thread {t.id}: turn/pending_yield disagree"
        assert t.lead, f"thread {t.id} has no lead"
    if story.main is not None:
        assert (story.main.turn == "resolved") == (story.phase in TERMINAL), "main thread is resolved iff the story is terminal"
    if story.phase in ACTIVE:
        assert story.ball == story.main.turn
    else:
        assert story.ball is None
