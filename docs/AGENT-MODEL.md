# The Story model — how humans and agents work together in zharn

*Design document, 2026-08-28, reworked 2026-08-30. This describes the interaction model the
whole program is built around. It deliberately says nothing about files, commands, or schemas;
those live in [`docs/specs/story-lifecycle.md`](specs/story-lifecycle.md).*

## 1. Why not a chat window

A chat window makes one agent the center of the work and the human its babysitter: you type at
it, wait, read, type again. Every improvement to that loop still leaves the human doing the
orchestration. zharn inverts it. **Work is a Story. The human is its Author. Agents are the
Cast.** The author describes and validates; the cast does everything in between, including
recruiting more cast.

Chat itself is not the enemy — chat as the *center of work* is. zharn keeps exactly one chat:
a **bare context**, a scratch conversation for questions ("what does this module do?") with no
story, no phases, no cast. The lab bench, not the workshop. The moment a chat drifts into real
work, it is promoted into a story. Work never lives in a chat. (An **aside** is the same lab
bench with borrowed memory: a bare context pinned to one comment — §2.)

## 2. Vocabulary

Three concepts carry the model, and each has a job the others cannot do. If two of them ever
collapse into the same thing, the model is wrong.

**Thread** — *what*: a root comment and its replies; one topic on a story. A thread has an
**author** (whoever opened it), a **lead** (the character its root comment addressed), and a
**turn** — whether the thread currently waits on its author, waits on its cast, or is
**resolved**: topic closed, nothing pending. The lead is the only character that yields in a
thread; anyone else taking part is a **guest**.

**Character** — *who*: a role instantiated on a story. A named participant with an inbox and an
attention, who posts comments *as itself* (e.g. "Reviewer · opus"), leads many threads over its
life, and holds exactly one **live context** at a time — recast replaces the context; the
character, its name, its threads, and its pending obligations all survive. A character **owes**
the threads it leads that wait on the cast, and **awaits** the threads and sub-stories it opened
that wait on theirs.

**Context** — *memory*: one agent conversation — system prompt, turns, tool calls — resumable,
forkable, viewable. What bb calls a thread. A context is owned by a character, by a minion, or
by the human (a **bare context**, started from the New Context button, belonging to no story).

The rest of the cast list:

**Story** — the smallest unit of work its author describes and validates. Stories live on the
board of a workspace, never inside a repository: the repositories a story touches follow from
where its cast chose to work. What happens inside a story is the cast's business, not the author's.

**Main thread** — a story's first thread, opened by Start. Its author is the story's author and
its lead is the protagonist. It is the story's spine: questions, the outline, handoffs, and the
replies to them all live here. **The story's ball is the main thread's turn.**

**Author** — whoever created a story (the human for board-level stories; a character for its
sub-stories). The only party who can approve it.

**Protagonist** — the first character, cast fresh at Start. The protagonist leads: it classifies
the work, decides who else to bring in, and is the only character that can yield on the main
thread — and therefore the only one that can move the story between phases or hand it back.

**Friend** — any other character, cast by a character or by the author opening a thread with a
role. Peers of the protagonist in every respect except the main thread. A friend may be a
**fork**: cast from another character's role with a copy of that character's memory at the
moment of casting — a second opinion, or an answer to a side question, from someone who already
knows everything the original knows, without touching the original's attention. A fork cannot
change the original's plan; it can only tell it.

**Guest** — a character taking part in a thread it neither leads nor opened, because it was
mentioned or simply commented. Guests owe nothing there.

**Minion** — a short-lived helper: a context with no character. No name, no comments; its result
returns to whoever dispatched it, and it may be *forked* from its dispatcher's context so it
starts knowing everything the dispatcher knows.

**Role** — the definition a character is cast from: provider, model, permission ceiling,
instructions, skills.

**Sub-story** — a story created by a character, who becomes its author. Recursive.

**Comment** — the only channel of communication on a story. Every comment belongs to a thread.

**Yield** — a character turning a thread over to that thread's author, with a **question** or a
**handoff** (a result: an outline, an answer, finished work). A yield flips the thread's turn;
on the main thread, that is the ball moving.

**Resolve** — a thread's author declaring its topic finished. The counterpart to Reply: both
answer a pending yield, but a reply hands the thread back to its cast while a resolve closes it,
waking nobody. A comment in a resolved thread reopens it.

**Inbox / attention** — a character attends one thread at a time: the thread of whatever was
last delivered to it. Everything else addressed to it queues in its inbox until it comes up for
air. Nobody can hijack a character's attention — but anyone can join the thread it is already
attending.

**Waiting / quiet** — a character that has a friend out or a sub-story open is **waiting** when
it stops: their yields will wake it. A character that stops while it still owes a thread and
awaits nothing has **gone quiet**, and the harness yields that thread for it, saying so.

**Recap** — a comment summarizing the state of the character's work — done, in flight, gotchas,
next — posted in the thread it is attending before its context is replaced.

**Recast** — replacing a character's live context with a fresh one built from the story record
and the latest recap. How a story survives a full context, a wedged session, or a mid-story
change of role or model. The character persists; only its memory is rebuilt.

**Aside** — a private chat pinned to one comment: a bare context forked from the memory that
wrote it, for the author's clarifying questions about that one message. True to its name, nobody
on the story hears it — an aside has no character, no thread, and no turn; it cannot speak or
act on the story, and nothing said in it enters the record. What should reach the story goes
into the author's reply.

## 3. Phases, the ball, and turns

A story's state is two facts: which **phase** it is in, and who holds the **ball** — and the
ball is nothing more than the main thread's turn.

```
phase ∈ backlog · todo · planning · implementing · done · canceled
ball  = main thread's turn ∈ cast · author     (only while planning or implementing)
```

| phase | ball with the cast | ball with the author → the author may |
|---|---|---|
| backlog, todo | — (no cast yet) | **Start** |
| planning | investigating, asking, outlining | **Reply** · **Proceed** to implementing |
| implementing | building the approved outline (or just building) | **Reply** (request changes) · **Approve** · **Back to planning** |
| done, canceled | — | **Reopen** |

Every other thread has the same two-sided turn, one level down: a friend's handoff flips *its*
thread to *its* author (often the character that called it in), and none of that touches the
ball. Three rules make the matrix honest:

* **Nobody sets status.** Phase, ball, and turns change only as side effects of the actions in
  §4. There is no "mark as done" for anyone, human or agent.
* **Required attention is a state; available attention is not.** The ball says who is *blocked*
  on whom. Anyone may open threads and comment at any time without moving the ball.
* **Attention is the character's own.** A reply in the thread a character is attending reaches
  it immediately — that is steering. Anything else waits in its inbox until it finishes its
  current turn — that is a "btw". The author chooses which one they are doing by where they
  write.

## 4. Actions

**The author** can: Start (an optional opening note and a choice of role for the protagonist) ·
Reply to a yield · Resolve a side thread waiting on them · Proceed · Approve · Back to planning ·
Cancel · Reopen · open a new thread
(to the protagonist by default, to `@Name`, or to a fresh friend via a role) · reply in any
thread · **Recast** any character (optionally onto a new role or model) · start a bare context ·
promote a bare context into a story.

**Any character** can: yield in a thread it leads · comment · open a thread · resolve a
thread it authored that waits on it · call in a friend, fresh or forked from itself · send out
minions · create a sub-story · post a recap · wait — stop for now while a friend or a sub-story is
out.

**Only a thread's lead** yields in it. The protagonist leads the main thread, so it alone moves
the story between phases or hands it back, and it alone Proceeds.

## 5. How a story unfolds

1. The author writes a story and presses **Start**, which opens the main thread; the description
   is the brief, the opening note its first comment.
2. The protagonist classifies the work — a spike, a bounded change, or something needing an
   outline — and may ask the author questions, batched, with choices where possible. Each
   question is a yield on the main thread: the ball moves to the author.
3. If an outline is needed, the protagonist hands it off; the author reads it and Proceeds,
   replies with changes, or sends it back. If not, the protagonist Proceeds on its own.
4. Implementing. The protagonist decides how the work gets done: itself, minions, friends,
   sub-stories (§6). A typical shape: a swarm of minions investigates; `call` opens a thread to
   an **Implementor** friend; the protagonist keeps working, then *waits*. The Implementor's
   handoff wakes the protagonist, who calls a **Reviewer** into a thread of its own — "review
   #2" — and waits again. The review comes back; the protagonist replies in the Implementor's
   thread with what to fix. Fixes go round once more.
5. Meanwhile the author may open a side thread to the protagonist — "why X and not Y?" — which
   waits in its inbox and gets answered between turns, without derailing the build; or the
   author asks a **fork** of the protagonist instead and gets the answer now. The author
   replies, or resolves the thread if the answer settles it. If the
   protagonist's context runs low, the harness tells it to recap, and the author (or the
   harness) recasts it: same character, fresh memory, its own recap and a brief that says where
   the record is.
6. The protagonist hands off on the main thread: what changed, how it was verified, where to
   look first, with the harness's check results attached. The ball moves to the author.
7. The author validates and Approves, or replies with what is wrong.

At no point did the author talk *to an agent*; they wrote in a story, and the cast responded.

## 6. Choosing how to decompose

A character has three tools for work it does not do itself:

| Use a… | when… |
|---|---|
| **minion** | you need a result and nobody needs to see the process |
| **friend** | others should see the contribution as a participant — a review, a second opinion, a parallel build |
| **sub-story** | the work should be described and validated on its own |

Sub-stories nest without limit, but one level is almost always enough. Delegation is also how a
character **protects its context**: minions read, friends build, sub-stories contain — the
protagonist holds the plot and stays thin. Recast is the recovery tool; delegation is why it is
rarely needed.

## 7. Communication rules

* Everything anyone says on a story is a comment in a thread, shown with its author.
* A root comment that addresses nobody opens a thread to the protagonist; `@Name` opens one to
  that character; opening with a role casts a fresh friend to lead it; opening with a fork of
  `@Name` casts a forked friend to lead it. A reply with no mention goes to the thread's lead; a
  reply to a yield goes to whoever yielded (to the lead, when the harness yielded for it).
  `@Name` anywhere brings Name in as a guest.
* Delivery follows attention: comments in a character's attended thread reach it immediately,
  even mid-turn; everything else queues in its inbox, oldest first, one per turn, delivered when
  the character stops. A waiting or idle character is woken by whatever arrives.
* An author's comment in a thread that is waiting on them **is** the reply — there is exactly
  one pending yield there, so there is nothing else it could mean. The turn flips back.
* A resolved thread is not locked: any comment in it reopens it. But once a story is done or
  canceled its threads are read-only — Reopen the story first.
* Cast talk never moves the ball; only main-thread yields and replies do.
* A question that offers choices is shown as choices; picking one answers it.
* A comment's author can be questioned privately: an **aside** on the comment forks its memory
  into a bare chat with the author, costing the character nothing. Clarify in the aside; answer
  on the thread — the reply is the only record.
* A character's context is viewable — thinking, tool calls, minions, and every predecessor
  context it had before a recast. Typing into a character's context view posts a comment into
  the thread it is attending: the same channel, a different skin. There is no hidden way to talk
  to a character. Minion contexts are read-only; a minion's output is its dispatcher's contract.

## 8. How the cast knows the rules

The harness owns the process, the tools the cast uses, and the words each character wakes up
with. **Anything that can be enforced mechanically is; skills exist only for judgment.**
Mechanically: status cannot be set; a character that goes quiet — stops owing a thread while
awaiting nothing — has that thread yielded by the harness, which says so; main-thread handoffs
while a sub-story is open are blocked;
a handoff in the implementing phase always carries the project's own checks, run by the harness;
delivery and inboxes are the harness's bookkeeping; a context running low triggers a recap
warning, and a character that can no longer be resumed — or whose author presses Recast — gets a
fresh context built from the story record and its latest recap, falling back gracefully when no
recap exists. A done or canceled story retires its cast: Cancel stops every context now,
Approve lets each finish the turn it is in.

For judgment, every character wakes up with a short set of iron laws and the skill for the phase
it is in — how to plan, how to implement, how to yield, how to delegate — and can reach the
discipline skills (test-driven development, systematic debugging, verification, code review)
when it needs them. The skills are files in your fork, adapted from superpowers; the harness
records what each character actually did, so a skill's effect is tested against facts rather
than transcripts.

The recap is the model's compaction story made honest: because comments are the only channel,
the durable state of a story already lives in its threads, curated and auditable — a replaced
context loses only residue. A recap carries the rest, and it too is just a comment.

## 9. What the author sees

* **The board**, by phase. Stories waiting on *you* are highlighted, say why (a question, an
  outline, a result, or a side thread waiting on your reply), sort first, and are counted at the
  top. Stories waiting on a character's author are muted. Stories the cast is working on show
  live activity.
* **A story page**: description and Start until it begins; then the current phase, whose turn it
  is, and the actions you have right now. Below, the threads — every character's contributions
  under their name, choices as buttons, handoffs with their evidence, an aside on any
  character's comment, resolved threads folded to their root and yields. Beside it, the cast with live status — working on which thread,
  waiting, idle, or retired; inbox depth, context meter, a Recast button — and the sub-stories
  with their own phase and ball.
* **A composer** in every thread, and one for opening new ones — steering, answering, calling in
  a friend or a fork. Never the center of the work.
* **Contexts**: a list of every conversation — characters' (with their recast lineage), bare
  ones and asides (pinned to their comment, listed under their story), minions' under their
  dispatcher — and a **New Context** button for a story-less chat.
  Every context view is interactive except a minion's; a character's input box is the comment
  channel in disguise (§7). A bare context that turns into work has a **Promote to story**
  button: the chat becomes the protagonist's context, and the work gets a story.

## 10. Boundaries

This document does not decide what Approve does to the code (merge, pull request, worktree
cleanup); that belongs with environments. Workspaces, repos, and environments — where a story
lives on disk and where a character stands when it works — are defined in
[`docs/specs/workspace-model.md`](specs/workspace-model.md). It does not decide execution on
other machines. It does not define roles beyond the handful shipped as examples, nor context
forking beyond minions.
