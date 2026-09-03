"""The pure state machine: every cell × every action of lifecycle spec §2, per-thread turns, rejections, §2.4 invariants."""
import copy
import itertools

import pytest

from harness.lifecycle import (ACTIVE, PHASES, TERMINAL, Approve, BackToPlanning, Cancel, Comment, Note, OpenThread,
                               Proceed, Recap, Rejected, Reopen, Reply, Resolve, Start, Story, Thread, Yield,
                               awaits, check_invariants, owes, step)

_ids = itertools.count(1)


def cid() -> str:
    return f"c{next(_ids)}"


def run(story, action):
    """step + invariants, returning (story, comment)."""
    s2, c = step(story, action, comment_id=cid(), now=1000.0)
    check_invariants(s2)
    return s2, c


def fresh(phase="todo") -> Story:
    return Story(key="ZH-1", title="T", description="D", phase=phase)


def started() -> Story:
    s, _ = run(fresh(), Start(thread_id="t1", protagonist="chr1", note="go"))
    return s


def at(phase, ball):
    """A started story driven to the requested (phase, ball) cell."""
    s = started()  # (planning, cast)
    if phase == "planning" and ball == "author":
        s, _ = run(s, Yield("t1", "chr1", "handoff", "outline"))
    elif phase == "implementing":
        s, _ = run(s, Proceed(by="chr1"))
        if ball == "author":
            s, _ = run(s, Yield("t1", "chr1", "handoff", "done"))
    elif phase == "done":
        s = at("implementing", "author")
        s, _ = run(s, Approve())
    elif phase == "canceled":
        s, _ = run(s, Cancel())
    assert (s.phase, s.ball) == (phase, ball if phase in ACTIVE else None)
    return s


# ---------------------------------------------------------------- purity, ball, serialization

def test_step_does_not_mutate_input():
    s = fresh()
    before = copy.deepcopy(s)
    step(s, Start(thread_id="t1", protagonist="chr1"), comment_id="c", now=1.0)
    assert s == before


def test_ball_is_derived_from_main_turn_only_while_active():
    assert fresh("backlog").ball is None and fresh("todo").ball is None
    s = started()
    assert s.ball == "cast" and s.main.turn == "cast"
    s, _ = run(s, Yield("t1", "chr1", "question", "?"))
    assert s.ball == "author"
    assert at("done", None).ball is None and at("canceled", None).ball is None


def test_to_dict_roundtrip_has_no_ball_key():
    s = at("planning", "author")
    d = s.to_dict()
    assert "ball" not in d
    assert d["threads"][0] == {"id": "t1", "author": "human", "lead": "chr1", "turn": "author", "pending_yield": d["threads"][0]["pending_yield"]}
    assert Story.from_dict(d) == s


# ---------------------------------------------------------------- Start

@pytest.mark.parametrize("phase", ["backlog", "todo"])
def test_start_opens_main_thread_casts_protagonist_and_moves_to_planning(phase):
    s, c = run(fresh(phase), Start(thread_id="t1", protagonist="chr1", note="opening note"))
    assert (s.phase, s.ball) == ("planning", "cast")
    assert s.protagonist == "chr1" and s.main_thread == "t1"
    assert s.main == Thread(id="t1", author="human", lead="chr1", turn="cast", pending_yield=None)
    assert c["kind"] == "text" and c["author"] == "human" and c["body"] == "opening note" and c["thread_id"] == "t1"
    assert c["reply_to"] is None and c["story_key"] == "ZH-1" and c["created_at"] == 1000.0 and c["id"].startswith("c")
    assert c["structured"]["transition"] == {"from": [phase, None], "to": ["planning", "cast"]}


def test_start_without_note_has_default_body():
    _, c = run(fresh(), Start(thread_id="t1", protagonist="chr1"))
    assert c["body"] == "Started."


@pytest.mark.parametrize("phase", ["planning", "implementing", "done", "canceled"])
def test_start_rejected_once_started(phase):
    s = at(phase, "cast" if phase in ACTIVE else None)
    with pytest.raises(Rejected, match="already started|terminal"):
        step(s, Start(thread_id="t9", protagonist="chr9"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Yield

@pytest.mark.parametrize("kind", ["question", "handoff"])
def test_yield_on_main_flips_ball_to_author_and_records_transition(kind):
    s = started()
    s, c = run(s, Yield("t1", "chr1", kind, "body", options=["a", "b"]))
    assert s.ball == "author" and s.main.pending_yield == c["id"]
    assert c["kind"] == kind and c["author"] == "chr1" and c["structured"]["options"] == ["a", "b"]
    assert c["structured"]["transition"] == {"from": ["planning", "cast"], "to": ["planning", "author"]}


def test_yield_twice_in_same_thread_is_rejected():
    s, _ = run(started(), Yield("t1", "chr1", "question", "?"))
    with pytest.raises(Rejected, match="already waits"):
        step(s, Yield("t1", "chr1", "question", "again"), comment_id="x", now=1.0)


def test_only_protagonist_yields_on_main():
    with pytest.raises(Rejected, match="only the thread's lead yields in it"):
        step(started(), Yield("t1", "chr2", "question", "?"), comment_id="x", now=1.0)


def test_yield_bad_kind_rejected():
    with pytest.raises(Rejected, match="kind"):
        step(started(), Yield("t1", "chr1", "status", "x"), comment_id="x", now=1.0)


def test_yield_unknown_thread_rejected():
    with pytest.raises(Rejected, match="thread"):
        step(started(), Yield("nope", "chr1", "question", "x"), comment_id="x", now=1.0)


def test_main_handoff_while_implementing_blocked_by_open_substories():
    s = at("implementing", "cast")
    with pytest.raises(Rejected, match="sub-stor"):
        step(s, Yield("t1", "chr1", "handoff", "done", open_substories=1), comment_id="x", now=1.0)
    s2, c = run(s, Yield("t1", "chr1", "question", "q", open_substories=1))  # questions are not blocked
    assert s2.ball == "author"


def test_implementing_handoff_carries_checks():
    s = at("implementing", "cast")
    checks = [{"repo": "r", "cmd": "pytest", "exit": 0, "output": "ok"}]
    _, c = run(s, Yield("t1", "chr1", "handoff", "done", checks=checks))
    assert c["structured"]["checks"] == checks


@pytest.mark.parametrize("phase", ["done", "canceled"])
def test_yield_on_terminal_story_rejected(phase):
    with pytest.raises(Rejected, match="terminal"):
        step(at(phase, None), Yield("t1", "chr1", "question", "?"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Reply

@pytest.mark.parametrize("phase", ["planning", "implementing"])
def test_reply_on_main_answers_the_pending_yield_and_returns_ball(phase):
    s = at(phase, "author")
    pending = s.main.pending_yield
    s, c = run(s, Reply("t1", "here you go"))
    assert (s.phase, s.ball) == (phase, "cast") and s.main.pending_yield is None
    assert c["kind"] == "text" and c["author"] == "human" and c["reply_to"] == pending
    assert c["structured"]["transition"] == {"from": [phase, "author"], "to": [phase, "cast"]}


def test_reply_when_thread_not_waiting_is_rejected():
    with pytest.raises(Rejected, match="not waiting"):
        step(started(), Reply("t1", "x"), comment_id="x", now=1.0)


def test_reply_by_non_author_is_rejected():
    s = at("planning", "author")
    with pytest.raises(Rejected, match="author"):
        step(s, Reply("t1", "x", by="chr1"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Proceed (both sides)

def test_author_proceed_from_planning_author_goes_to_implementing_cast():
    s = at("planning", "author")
    s, c = run(s, Proceed(by="human", note="looks good"))
    assert (s.phase, s.ball) == ("implementing", "cast") and s.main.pending_yield is None
    assert c["kind"] == "system" and c["author"] == "human" and "outline approved" in c["body"] and "looks good" in c["body"]
    assert c["structured"]["transition"] == {"from": ["planning", "author"], "to": ["implementing", "cast"]}


def test_protagonist_proceed_from_planning_cast_goes_to_implementing_cast():
    s, c = run(started(), Proceed(by="chr1"))
    assert (s.phase, s.ball) == ("implementing", "cast")
    assert c["kind"] == "system" and c["author"] == "chr1"
    assert c["structured"]["transition"] == {"from": ["planning", "cast"], "to": ["implementing", "cast"]}


def test_author_proceed_while_ball_with_cast_is_rejected():
    with pytest.raises(Rejected):
        step(started(), Proceed(by="human"), comment_id="x", now=1.0)


def test_protagonist_proceed_while_ball_with_author_is_rejected():
    with pytest.raises(Rejected):
        step(at("planning", "author"), Proceed(by="chr1"), comment_id="x", now=1.0)


def test_stranger_proceed_is_rejected():
    with pytest.raises(Rejected, match="protagonist|author"):
        step(started(), Proceed(by="chr9"), comment_id="x", now=1.0)


@pytest.mark.parametrize("phase,ball", [("implementing", "cast"), ("implementing", "author"), ("done", None), ("canceled", None), ("todo", None)])
def test_proceed_outside_planning_is_rejected(phase, ball):
    s = at(phase, ball) if phase != "todo" else fresh()
    with pytest.raises(Rejected):
        step(s, Proceed(by="human"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Approve / Back to planning

def test_approve_from_implementing_author_goes_to_done():
    s = at("implementing", "author")
    s, c = run(s, Approve(note="ship it"))
    assert (s.phase, s.ball) == ("done", None) and s.main.pending_yield is None
    assert c["kind"] == "system" and "ship it" in c["body"]
    assert c["structured"]["transition"] == {"from": ["implementing", "author"], "to": ["done", None]}


def test_back_to_planning_from_implementing_author():
    s = at("implementing", "author")
    s, c = run(s, BackToPlanning(note="rethink"))
    assert (s.phase, s.ball) == ("planning", "cast")
    assert c["structured"]["transition"] == {"from": ["implementing", "author"], "to": ["planning", "cast"]}


@pytest.mark.parametrize("action", [Approve(), BackToPlanning()])
@pytest.mark.parametrize("phase,ball", [("planning", "cast"), ("planning", "author"), ("implementing", "cast"), ("done", None), ("canceled", None)])
def test_approve_and_back_rejected_outside_implementing_author(action, phase, ball):
    with pytest.raises(Rejected):
        step(at(phase, ball), action, comment_id="x", now=1.0)


def test_approve_by_non_author_rejected():
    with pytest.raises(Rejected, match="author"):
        step(at("implementing", "author"), Approve(by="chr1"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Cancel / Reopen

@pytest.mark.parametrize("phase,ball", [("planning", "cast"), ("planning", "author"), ("implementing", "cast"), ("implementing", "author")])
def test_cancel_from_any_active_cell(phase, ball):
    s, c = run(at(phase, ball), Cancel(note="nah"))
    assert (s.phase, s.ball) == ("canceled", None)
    assert c["structured"]["transition"] == {"from": [phase, ball], "to": ["canceled", None]}


def test_cancel_unstarted_story():
    s, c = run(fresh("backlog"), Cancel())
    assert s.phase == "canceled" and s.main_thread is None
    assert c["thread_id"] is None


@pytest.mark.parametrize("phase", TERMINAL)
def test_cancel_terminal_rejected(phase):
    with pytest.raises(Rejected, match="terminal"):
        step(at(phase, None), Cancel(), comment_id="x", now=1.0)


@pytest.mark.parametrize("phase", TERMINAL)
def test_reopen_started_story_goes_to_implementing_cast(phase):
    s, c = run(at(phase, None), Reopen(note="one more thing"))
    assert (s.phase, s.ball) == ("implementing", "cast")
    assert "one more thing" in c["body"] and c["thread_id"] == "t1"
    assert c["structured"]["transition"] == {"from": [phase, None], "to": ["implementing", "cast"]}


def test_reopen_never_started_story_goes_back_to_todo():
    s, _ = run(fresh("backlog"), Cancel())
    s, c = run(s, Reopen(note="again"))
    assert s.phase == "todo" and s.protagonist is None
    assert c["structured"]["transition"] == {"from": ["canceled", None], "to": ["todo", None]}


@pytest.mark.parametrize("phase,ball", [("planning", "cast"), ("implementing", "author")])
def test_reopen_non_terminal_rejected(phase, ball):
    with pytest.raises(Rejected, match="terminal"):
        step(at(phase, ball), Reopen(note="x"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Threads beyond main

def test_open_thread_creates_thread_with_author_and_lead_no_transition():
    s = started()
    s, c = run(s, OpenThread(thread_id="t2", author="human", lead="chr1", body="why X?"))
    assert s.thread("t2") == Thread(id="t2", author="human", lead="chr1", turn="cast", pending_yield=None)
    assert s.ball == "cast" and "transition" not in c["structured"]
    assert c["kind"] == "text" and c["thread_id"] == "t2" and c["reply_to"] is None


def test_open_thread_before_start_or_after_terminal_rejected():
    with pytest.raises(Rejected):
        step(fresh(), OpenThread(thread_id="t2", author="human", lead="chr1", body="x"), comment_id="x", now=1.0)
    with pytest.raises(Rejected):
        step(at("done", None), OpenThread(thread_id="t2", author="human", lead="chr1", body="x"), comment_id="x", now=1.0)


def test_open_thread_duplicate_id_rejected():
    with pytest.raises(Rejected, match="exists"):
        step(started(), OpenThread(thread_id="t1", author="human", lead="chr1", body="x"), comment_id="x", now=1.0)


def test_side_thread_yield_and_reply_never_touch_the_ball():
    s, _ = run(started(), OpenThread(thread_id="t2", author="human", lead="chr2", body="review?"))
    s, c = run(s, Yield("t2", "chr2", "handoff", "LGTM"))
    assert s.thread("t2").turn == "author" and s.ball == "cast" and "transition" not in c["structured"]
    s, c = run(s, Reply("t2", "thanks"))
    assert s.thread("t2").turn == "cast" and s.ball == "cast" and "transition" not in c["structured"]


def test_side_thread_yield_by_thread_author_rejected():
    s, _ = run(started(), OpenThread(thread_id="t2", author="chr1", lead="chr2", body="do it"))
    with pytest.raises(Rejected, match="only the thread's lead yields in it"):
        step(s, Yield("t2", "chr1", "handoff", "x"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Resolve


def waiting_side_thread(author="human", lead="chr2"):
    """A started story with side thread t2 yielded back to its author; returns (story, yield comment)."""
    s, _ = run(started(), OpenThread(thread_id="t2", author=author, lead=lead, body="why X?"))
    return run(s, Yield("t2", lead, "handoff", "because Y"))


def test_resolve_closes_the_pending_yield_without_waking_anyone():
    s, y = waiting_side_thread()
    s, c = run(s, Resolve(thread_id="t2", by="human", note="settled, thanks"))
    t = s.thread("t2")
    assert t.turn == "resolved" and t.pending_yield is None
    assert c["kind"] == "system" and "settled, thanks" in c["body"] and c["reply_to"] == y["id"]
    assert s.ball == "cast" and "transition" not in c["structured"]


def test_character_resolves_a_thread_it_authored():
    s, _ = waiting_side_thread(author="chr1", lead="chr2")
    s, c = run(s, Resolve(thread_id="t2", by="chr1"))
    assert s.thread("t2").turn == "resolved" and c["author"] == "chr1"


def test_resolve_main_thread_rejected():
    s = at("planning", "author")
    with pytest.raises(Rejected, match="main"):
        step(s, Resolve(thread_id="t1", by="human"), comment_id="x", now=1.0)


def test_resolve_while_waiting_on_cast_rejected():
    s, _ = run(started(), OpenThread(thread_id="t2", author="human", lead="chr2", body="why?"))
    with pytest.raises(Rejected, match="cast"):
        step(s, Resolve(thread_id="t2", by="human"), comment_id="x", now=1.0)


def test_resolve_by_non_author_rejected():
    s, _ = waiting_side_thread()
    with pytest.raises(Rejected, match="author"):
        step(s, Resolve(thread_id="t2", by="chr2"), comment_id="x", now=1.0)


def test_resolve_already_resolved_or_unknown_thread_rejected():
    s, _ = waiting_side_thread()
    s, _ = run(s, Resolve(thread_id="t2", by="human"))
    with pytest.raises(Rejected):
        step(s, Resolve(thread_id="t2", by="human"), comment_id="x", now=1.0)
    with pytest.raises(Rejected, match="thread"):
        step(s, Resolve(thread_id="zz", by="human"), comment_id="x", now=1.0)


def test_resolve_on_terminal_story_rejected():
    s = at("implementing", "author")
    s, _ = run(s, OpenThread(thread_id="t2", author="human", lead="chr2", body="q"))
    s, _ = run(s, Yield("t2", "chr2", "handoff", "a"))
    s, _ = run(s, Approve())
    with pytest.raises(Rejected, match="terminal"):
        step(s, Resolve(thread_id="t2", by="human"), comment_id="x", now=1.0)


def test_approve_resolves_every_open_thread_main_included():
    s = at("implementing", "author")
    s, _ = run(s, OpenThread(thread_id="t2", author="human", lead="chr2", body="q"))
    s, _ = run(s, Yield("t2", "chr2", "handoff", "a"))                        # waits on the human
    s, _ = run(s, OpenThread(thread_id="t3", author="chr1", lead="chr3", body="do"))  # waits on cast
    s, _ = run(s, Approve())
    assert all(t.turn == "resolved" and t.pending_yield is None for t in s.threads)


def test_cancel_resolves_every_open_thread_main_included():
    s = at("implementing", "cast")
    s, _ = run(s, OpenThread(thread_id="t2", author="human", lead="chr2", body="q"))
    s, _ = run(s, Yield("t2", "chr2", "handoff", "a"))
    s, _ = run(s, Cancel())
    assert all(t.turn == "resolved" and t.pending_yield is None for t in s.threads)


def test_comment_in_resolved_thread_reopens_it_to_cast():
    s, _ = waiting_side_thread()
    s, _ = run(s, Resolve(thread_id="t2", by="human"))
    s, c = run(s, Comment("t2", "human", "actually, one more thing"))
    assert s.thread("t2").turn == "cast" and c["kind"] == "text" and c["reply_to"] is None


def test_yield_in_resolved_thread_reopens_it_straight_to_author():
    s, _ = waiting_side_thread()
    s, _ = run(s, Resolve(thread_id="t2", by="human"))
    s, c = run(s, Yield("t2", "chr2", "question", "one more?"))
    assert s.thread("t2").turn == "author" and s.thread("t2").pending_yield == c["id"]


@pytest.mark.parametrize("phase", TERMINAL)
def test_comment_in_thread_of_terminal_story_rejected(phase):
    with pytest.raises(Rejected, match="terminal"):
        step(at(phase, None), Comment("t1", "human", "x"), comment_id="x", now=1.0)


def test_recap_on_terminal_story_rejected():
    with pytest.raises(Rejected, match="terminal"):
        step(at("canceled", None), Recap(by="chr1", body="x"), comment_id="x", now=1.0)


def test_reopen_unresolves_main_but_leaves_side_threads_resolved():
    s = at("implementing", "author")
    s, _ = run(s, OpenThread(thread_id="t2", author="human", lead="chr2", body="q"))
    s, _ = run(s, Yield("t2", "chr2", "handoff", "a"))
    s, _ = run(s, Approve())
    s, _ = run(s, Reopen(note="more"))
    assert s.main.turn == "cast" and s.thread("t2").turn == "resolved"


def test_invariants_catch_resolved_thread_with_pending_yield():
    s, _ = waiting_side_thread()
    s, _ = run(s, Resolve(thread_id="t2", by="human"))
    s.thread("t2").pending_yield = "c9"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_resolved_main_on_active_story():
    s = started()
    s.main.turn = "resolved"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_unresolved_main_on_terminal_story():
    s = at("done", None)
    s.main.turn = "cast"
    with pytest.raises(AssertionError):
        check_invariants(s)


# ---------------------------------------------------------------- Comment / Recap

def test_comment_in_thread_waiting_on_commenter_is_a_reply():
    s = at("planning", "author")
    s, c = run(s, Comment("t1", "human", "answer"))
    assert s.ball == "cast" and c["reply_to"] is not None


def test_comment_otherwise_is_plain_text_with_no_transition():
    s = started()
    s2, c = run(s, Comment("t1", "human", "btw"))
    assert s2 == s and c["kind"] == "text" and c["reply_to"] is None and "transition" not in c["structured"]
    s3, c = run(s, Comment("t1", "chr1", "working on it"))
    assert s3 == s and c["author"] == "chr1"


def test_comment_unknown_thread_rejected():
    with pytest.raises(Rejected, match="thread"):
        step(started(), Comment("zz", "human", "x"), comment_id="x", now=1.0)


def test_recap_posts_on_main_without_state_change():
    s = at("implementing", "cast")
    s2, c = run(s, Recap(by="chr1", body="done: a; next: b"))
    assert s2 == s and c["kind"] == "recap" and c["thread_id"] == "t1" and c["author"] == "chr1"


def test_recap_before_start_rejected():
    with pytest.raises(Rejected, match="started"):
        step(fresh(), Recap(by="chr1", body="x"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- invariants

def test_invariants_catch_turn_without_pending_yield():
    s = started()
    s.main.turn = "author"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_pending_yield_without_turn():
    s = started()
    s.main.pending_yield = "c9"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_active_phase_without_main_thread():
    s = fresh()
    s.phase = "planning"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_bad_phase():
    s = fresh()
    s.phase = "in_progress"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_every_phase_transition_has_exactly_one_causing_comment():
    """Walk a full life; count transitions in comments == number of phase/ball changes."""
    s = fresh()
    log = []
    for a in [Start(thread_id="t1", protagonist="chr1"), Comment("t1", "chr1", "hi"),
              Yield("t1", "chr1", "question", "?"), Reply("t1", "a"), Yield("t1", "chr1", "handoff", "plan"),
              Proceed(by="human"), Recap(by="chr1", body="r"), Yield("t1", "chr1", "handoff", "built"),
              BackToPlanning(), Proceed(by="chr1"), Yield("t1", "chr1", "handoff", "built2"), Approve(), Reopen(note="x"), Cancel()]:
        before = (s.phase, s.ball)
        s, c = run(s, a)
        after = (s.phase, s.ball)
        log.append((before != after, "transition" in c["structured"]))
    assert all(changed == recorded for changed, recorded in log), log
    assert sum(1 for changed, _ in log if changed) == 12  # every action above except Comment and Recap


def test_every_comment_has_a_context_slot_the_reducer_leaves_empty():
    s = started()
    _, c = run(s, Comment(thread_id="t1", by="chr1", body="hi"))
    assert "context" in c and c["context"] is None


# ---------------------------------------------------------------- leads, harness yields, recaps, notes (characters plan)

def with_friend():
    """(planning, cast) plus side thread t2: human → chr2."""
    s = started()
    s, _ = run(s, OpenThread(thread_id="t2", author="human", lead="chr2", body="review this"))
    return s


def test_only_the_threads_lead_yields_in_it():
    s = with_friend()
    with pytest.raises(Rejected, match="only the thread's lead yields in it"):
        run(s, Yield("t2", "chr1", "handoff", "not mine"))
    with pytest.raises(Rejected, match="only the thread's lead yields in it"):
        run(s, Yield("t1", "chr2", "handoff", "not mine either"))
    s2, c = run(s, Yield("t2", "chr2", "handoff", "done"))
    assert s2.thread("t2").turn == "author" and c["author"] == "chr2"


def test_the_harness_yields_for_the_lead():
    s = with_friend()
    with pytest.raises(Rejected, match="harness yields only for the thread's lead"):
        run(s, Yield("t2", "system", "handoff", "went quiet", auto_for="chr1"))
    s2, c = run(s, Yield("t2", "system", "handoff", "chr2 went quiet: last words", auto_for="chr2"))
    assert s2.thread("t2").turn == "author" and c["author"] == "system" and c["kind"] == "handoff"
    assert c["structured"]["auto_for"] == "chr2"
    s3, _ = run(s2, Reply(thread_id="t2", body="carry on", by="human"))  # the author replies as usual
    assert s3.thread("t2").turn == "cast"


def test_recap_lands_in_the_given_thread_or_main():
    s = with_friend()
    _, c = run(s, Recap(by="chr2", body="cleared A", thread_id="t2"))
    assert c["thread_id"] == "t2" and c["kind"] == "recap"
    _, c = run(s, Recap(by="chr1", body="on main"))
    assert c["thread_id"] == "t1"


def test_note_is_a_system_comment_that_moves_nothing():
    s = with_friend()
    s2, c = run(s, Note(thread_id="t1", body="recast protagonist (rung 1)"))
    assert c["author"] == "system" and c["kind"] == "system" and c["body"] == "recast protagonist (rung 1)"
    assert [t.turn for t in s2.threads] == [t.turn for t in s.threads] and s2.phase == s.phase
    canceled, _ = run(s, Cancel())
    with pytest.raises(Rejected, match="terminal"):
        run(canceled, Note(thread_id="t1", body="x"))


def test_a_thread_cannot_be_opened_to_its_own_author():
    with pytest.raises(Rejected, match="cannot be opened to its own author"):
        run(started(), OpenThread(thread_id="t2", author="chr1", lead="chr1", body="me"))


def test_owes_and_awaits_are_read_off_turns():
    s = with_friend()
    s, _ = run(s, OpenThread(thread_id="t3", author="chr1", lead="chr3", body="build it"))
    assert [t.id for t in owes(s, "chr1")] == ["t1"] and [t.id for t in awaits(s, "chr1")] == ["t3"]
    assert [t.id for t in owes(s, "chr3")] == ["t3"] and awaits(s, "chr3") == []
    s, _ = run(s, Yield("t3", "chr3", "handoff", "built"))
    assert owes(s, "chr3") == [] and awaits(s, "chr1") == []          # waiting on chr1 now
    s, _ = run(s, Yield("t1", "chr1", "question", "which?"))
    assert owes(s, "chr1") == []


def test_story_repos_round_trip():
    from harness.lifecycle import Story
    s = Story(key="ZH-1", title="t", repos=["client"])
    d = s.to_dict()
    assert d["repos"] == ["client"]
    assert Story.from_dict({"key": "ZH-2", "title": "u"}).repos == []
    assert Story.from_dict(d).repos == ["client"]
