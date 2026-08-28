# The Story model — how humans and agents work together in my-harness

*Design document, 2026-08-28. This describes the interaction model the whole program is built
around. It deliberately says nothing about files, commands, or schemas; those live in
`docs/superpowers/specs/2026-08-28-story-lifecycle-design.md`.*

## 1. Why not a chat window

A chat window makes one agent the center of the work and the human its babysitter: you type at
it, wait, read, type again. Every improvement to that loop still leaves the human doing the
orchestration. my-harness inverts it. **Work is a Story. The human is its Author. Agents are the
Cast.** The author describes and validates; the cast does everything in between, including
recruiting more cast. There is no chat box anywhere in the program.

## 2. Vocabulary

**Story** — the smallest unit of work its author describes and validates. Stories live on a
board. What happens inside a story (decomposition, helpers, retries, reviews) is the cast's
business, not the author's.

**Author** — whoever created a story. The human, for board-level stories; a character, for the
sub-stories it creates. The author is the only party who can approve a story.

**Cast** — the characters on a story.

**Character** — a role instantiated on a story. A named participant with its own conversation,
who posts comments *as itself* (e.g. "Reviewer · opus"), can address other characters, can ask
the author questions, and can be resumed at any point in the story's life.

**Protagonist** — the first character, cast when the author starts the story. The protagonist
leads: it classifies the work, decides who else to bring in, and is the only character that can
move the story between phases or hand it back to the author.

**Friend** — any character other than the protagonist, called in by a character or by the author.
Friends are the protagonist's peers in every respect except leadership.

**Minion** — a short-lived helper dispatched by a character. Not a participant: it has no name on
the story, cannot comment, and returns its result to whoever dispatched it. Sent out in swarms
for investigation, or alone for a bounded implementation step. A minion's output is its
dispatcher's responsibility; if a minion hits a question, the dispatcher decides whether to ask
the author.

**Role** — the definition a character is cast from: provider, model, permission ceiling,
instructions, skills. Implementor, Planner, Reviewer, Researcher, and whatever your fork adds.

**Sub-story** — a story created by a character, who becomes its author. Sub-stories obey every
rule in this document recursively.

**Comment** — the only channel of communication on a story. Comments are threaded: top-level
comments and replies beneath them.

**Yield** — a character handing the ball to the author, either with a **question** or with a
**handoff** (a finished phase: an outline for approval, or a result for validation).

## 3. Phases and the ball

A story's state is two facts: which **phase** it is in, and who holds the **ball**.

```
phase ∈ backlog · todo · planning · implementing · done · canceled
ball  ∈ cast · author            (only while planning or implementing)
```

| phase | ball with the cast | ball with the author → the author may |
|---|---|---|
| backlog, todo | — (no cast yet) | **Start** |
| planning | investigating, asking, outlining | **Reply** · **Proceed** to implementing |
| implementing | building the approved outline (or just building) | **Reply** (request changes) · **Approve** · **Back to planning** |
| done, canceled | — | **Reopen** |

Two rules make this matrix honest:

* **Nobody sets status.** Phase and ball change only as side effects of the actions in §4. There
  is no "mark as done" for anyone, human or agent.
* **Required attention is a state; available attention is not.** The ball says who is *blocked*
  on whom. Anyone may comment at any time without moving the ball — the author can steer while the
  cast works, and the cast can talk among themselves while the author thinks.

## 4. Actions

**The author** can: Start (with an optional opening note and a choice of role for the
protagonist) · Reply to a yield · Proceed · Approve · Back to planning · Cancel · Reopen ·
Comment without moving the ball · Call in a friend.

**Any character** can: ask the author a question · comment · address another character ·
call in a friend · send out minions · create a sub-story · wait for a character to speak or a
sub-story to come back.

**Only the protagonist** can: Proceed, and hand off.

**The harness itself** guarantees that a story never strands: if the whole cast goes quiet
without yielding, the harness yields on their behalf and says so; a protagonist cannot hand off
while any of its sub-stories is still open; a handoff in the implementing phase always carries
the project's own checks, run by the harness, not reported by the agent; a protagonist that can
no longer be resumed is recast from the story's record.

## 5. How a story unfolds

1. The author writes a story and presses **Start**. The description is the brief; an opening note
   is optional.
2. The protagonist reads the story and **classifies** it, the way superpowers' brainstorming does:
   a spike (answer a question), a bounded change (do it), or something that needs an outline
   first. It may ask the author questions — batched, with choices where possible — and the story
   waits on the author until they answer.
3. If an outline is needed, the protagonist hands it off; the author reads it in the comments and
   Proceeds, replies with changes, or sends it back. If not, the protagonist Proceeds on its own.
4. Implementing. The protagonist decides how the work gets done: itself, via minions, via
   friends, or via sub-stories (§6). A typical shape: it sends a swarm of minions to investigate,
   calls in an **Implementor** friend for the build, keeps working on something else, then
   *waits* for the Implementor. When the Implementor posts its result, the protagonist calls in
   a **Reviewer**, waits again, and the review appears as a reply beneath the Implementor's
   comment, authored by the Reviewer. Fixes go round once more.
5. The protagonist hands off: what changed, how it was verified, where the author should look
   first, with the harness's check results attached. The story waits on the author.
6. The author validates — visually or in the code — and Approves, or replies with what is wrong.

At no point did the author talk *to an agent*; they wrote in a story, and the cast responded.

## 6. Choosing how to decompose

A character has three tools for work it does not do itself. The rule of thumb:

| Use a… | when… |
|---|---|
| **minion** | you need a result and nobody needs to see the process |
| **friend** | others should see the contribution as a participant — a review, a second opinion, a parallel build |
| **sub-story** | the work should be described and validated on its own |

Sub-stories nest without limit, but one level is almost always enough.

## 7. Communication rules

* Everything anyone says on a story is a comment, shown with its author.
* A reply goes to the character that wrote the comment it replies to. A top-level comment that
  addresses nobody goes to the protagonist. `@Name` addresses a specific character.
* Cast talk never moves the ball; only yields to the author do.
* A question that offers choices is shown as choices; picking one answers it.
* A character's conversation — its thinking, tool calls, minion transcripts — is viewable but
  read-only. It exists for curiosity and audit, never for driving the character.

## 8. How the cast knows the rules

The harness owns the process, the tools the cast uses, and the words each character wakes up
with, so it never has to *ask* an agent to keep the story straight. **Anything that can be
enforced mechanically is; skills exist only for judgment.** Status cannot be set, handoffs are
blocked while sub-stories are open, checks are attached automatically, silence is auto-yielded.

For judgment, every character wakes up with a short set of iron laws and the skill for the phase
it is in — how to plan (classify, ask, outline), how to implement (test first, decompose, verify,
hand off with evidence), how to yield (answerable in thirty seconds), how to delegate (§6) —
and can reach the discipline skills (test-driven development, systematic debugging,
verification, code review) when it needs them. The skills are files in your fork, adapted from
superpowers; the harness records what each character actually did, so a skill's effect is
tested against facts rather than transcripts.

## 9. What the author sees

* **The board**, by phase. Stories waiting on *you* are highlighted, say why (a question, an
  outline, a result), sort first, and are counted at the top. Stories waiting on a character's
  author are muted. Stories the cast is working on show live activity.
* **A story page**: description and Start until it begins; then the current phase, whose turn it
  is, and the actions you have right now. Below, the comment stream — every character's
  contributions under their name, threaded replies, choices as buttons, handoffs with their
  evidence. Beside it, the cast with live status and links to their read-only conversations,
  and the sub-stories with their own phase and ball.
* **A composer** for comments — steering, answering, calling in a friend. Never a chat box.

## 10. Boundaries

This document does not decide what Approve does to the code (merge, pull request, worktree
cleanup); that belongs with environments. It does not decide execution on other machines. It
does not define roles beyond the handful shipped as examples.
