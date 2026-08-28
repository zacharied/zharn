# Task lifecycle — design spec (2026-08-28)

This document is declarative: it describes how my-harness *ought to* behave. Where the running
code disagrees, the code is wrong. It supersedes `docs/DESIGN.md` §3b.

## 0. Principles

1. **A Task is the smallest unit of work its owner describes and validates.** What happens inside
   a task (decomposition, helpers, retries) is the worker's business.
2. **Nobody sets status.** State changes are side effects of actions. There is no "set status"
   verb for agents or humans.
3. **Every human↔agent utterance is a comment on a task.** There is no chat input anywhere.
   Thread transcripts are a read-only projection.
4. **Required attention is a state; available attention is not.** The ball says who is blocked
   on whom. Anyone may comment at any time without moving the ball.
5. **Enforce mechanically what can be enforced; use skills only for judgment.** The harness owns
   the process, the CLI, and the system prompt, so it never has to *ask* an agent to keep state
   accurate.
6. **Fork-as-config applies to skills.** The rules agents follow are files in your fork.

## 1. State model

A task's state is `(phase, ball)`.

```
phase ∈ backlog | todo | planning | implementing | done | canceled
ball  ∈ worker | owner          # defined only while phase ∈ {planning, implementing}
```

* **Owner** — whoever created the task: the human for board-level tasks, the creating thread for
  agent-created subtasks (§5). Stored as `owner: "human" | <thread_id>`.
* **Worker** — the set of threads attached to the task (§3). "Ball with worker" means some thread
  is expected to act.

The matrix, with the owner's available actions in owner-ball cells:

| phase | ball = worker | ball = owner → owner may |
|---|---|---|
| `backlog`, `todo` | — (no thread yet) | **Start** |
| `planning` | investigating, drafting spec | **Reply** · **Proceed** |
| `implementing` | implementing (the approved spec, if one exists) | **Reply** (a.k.a. request changes) · **Approve** · **Back to planning** |
| `done`, `canceled` | terminal, no ball | **Reopen** |

`backlog` vs `todo` is a human triage distinction only; both mean "not started". `canceled` is
reachable from any non-terminal phase via **Cancel**.

## 2. Transitions

All transitions are caused by one of the actions below. Each action appends a comment (§4); the
comment stream is the complete audit log of a task.

### 2.1 Owner actions (UI buttons, or CLI verbs for thread owners)

| Action | Precondition | Effect |
|---|---|---|
| **Start** `[prompt]` `[preset]` | phase ∈ {backlog, todo} | Spawn the primary thread with the task brief (§3.2). If `prompt` given it becomes the first comment and the first user message; otherwise the description *is* the brief. → `(planning, worker)`. |
| **Reply** to a yield comment | ball = owner | Append reply; resume the authoring thread with the reply text. → `(same phase, worker)`. |
| **Proceed** `[note]` | `(planning, owner)` | Append system comment "approved for implementation" (+ note); resume primary thread. → `(implementing, worker)`. |
| **Approve** `[note]` | `(implementing, owner)` | Append system comment; threads are *not* resumed. → `(done, —)`. |
| **Back to planning** `[note]` | `(implementing, owner)` | Append system comment; resume primary thread with the note. → `(planning, worker)`. |
| **Cancel** `[note]` | phase non-terminal | Stop all threads on the task (and cancel open subtasks). → `(canceled, —)`. |
| **Reopen** `note` | phase terminal | Resume primary thread with the note. → `(implementing, worker)`. |
| **Comment** (top-level or reply) | ball = worker | Inject into the target thread (§3.3) as a mid-turn user message. **No state change.** |

### 2.2 Worker actions (`harness task …` CLI, run inside a thread)

| Verb | Precondition | Effect |
|---|---|---|
| `yield --question --body … [--options a,b,c]` | ball = worker | Append `question` comment. → `(same phase, owner)`. |
| `yield --handoff --body … [--attach path…]` | ball = worker; **no non-terminal subtasks** | Append `handoff` comment. In `implementing`, the harness first runs the project's check command (config: `CHECK_CMD`) and attaches its exit code + output to the comment. → `(same phase, owner)`. |
| `proceed [--note …]` | `(planning, worker)`; if the preset has `plan_first: true`, a planning handoff must have been Proceed-ed by the owner | Append system comment. → `(implementing, worker)`. The verb's stdout is the `implementing-a-task` skill (§6.3). |
| `comment --body … [--reply-to id] [--attach …]` | any | Append `text` comment. No state change. Use for milestones. |
| `create --title … [--description …] [--start --preset …]` | any | Create a subtask owned by this thread (§5). |
| `wait <key> [--timeout s]` | this thread owns `<key>` | Block until `<key>` moves to `(…, owner)` or a terminal phase; print the triggering comment. |
| `reply <key> --comment <id> --body …`, `proceed <key>`, `approve <key>`, `cancel <key>` | this thread owns `<key>` | Owner actions from §2.1 applied by a thread. **Rejected** for tasks the thread does not own. |
| `show [<key>]`, `list` | any | Read-only. |

There is no `task status` verb. `thread spawn/list/show/wait/send/stop` remain as today (§3.1).

### 2.3 Harness-driven transitions

| Trigger | Effect |
|---|---|
| The last running thread on a task exits (any exit code) while ball = worker | **Auto-handoff**: append system comment "thread ended without a handoff" (with the thread's last assistant text) → `(same phase, owner)`. A silent stop never strands a task. |
| A subtask reaches `(…, owner)` or a terminal phase | Its owner thread is notified: if blocked in `task wait`, the wait returns; otherwise the thread is resumed with the triggering comment as a user message. |
| Owner (human) acts on a subtask whose owner is a thread | Allowed ("butt in"). The transition is applied and the owning thread is notified with the resulting system comment. |

### 2.4 Invariants

* `ball` is `null` iff `phase ∈ {backlog, todo, done, canceled}`.
* A task in `(implementing, owner)` with a `handoff` as its latest yield is "ready for review"; in
  `(planning, owner)` with a `handoff` it is "spec ready". A latest yield of kind `question` in
  either phase is "has a question". These three are the only "needs you" flavors the UI shows.
* A parent cannot hand off while any child is non-terminal (checked in `yield --handoff`).
* A task never has a pending yield while ball = worker.
* Every state change has exactly one comment that caused it (the comment records the
  `(phase, ball)` before and after).

## 3. Threads

### 3.1 Attachment

A task has zero or more threads. The thread created by **Start** is the **primary thread**
(`primary_thread_id`). Further threads are attached by:

* the owner typing `/call <preset> [prompt]` in the comment box — spawns a thread whose brief is
  the task brief plus the full comment history; the `/call` line is stored as a `system` comment;
* a worker running `harness thread spawn --preset … --prompt …` (child of the calling thread, same
  task, as today).

All threads on a task are collectively "the worker"; any of them may `yield`, `proceed`, or
`comment`. Native subagents (Claude's `Agent` tool) are still available for invisible throwaway
work and are not threads.

### 3.2 Brief

The prompt a new thread receives: task key + title + description, the ordered comment stream
(rendered as markdown with authors and kinds), subtasks with their `(phase, ball)`, attachments,
followed by the preset's instructions and the ad-hoc prompt. The report-back contract lives in the
system prompt, not the brief (§6.3).

### 3.3 Routing rule

**A reply goes to the thread that authored the comment it replies to. A top-level comment goes to
the primary thread.** If the target thread is not running, it is resumed (`--resume` session). If
it cannot be resumed (session lost, provider gone), a fresh thread is spawned with the brief and
becomes the primary thread; a `system` comment records the replacement.

### 3.4 Transcript

Each thread has a read-only transcript view (thinking, tool calls, streamed text, cost), opened
from the task tab. It has no input box.

## 4. Comments

```
Comment
  id, task_key, parent_comment_id | null,
  author: "human" | <thread_id> | "system",
  kind:   text | question | handoff | system,
  body:   markdown,
  structured: { options?: [str], answers?: [str],       # question
                check?: {cmd, exit, output},            # handoff (implementing)
                transition?: {from: [phase, ball], to: [phase, ball]} }   # any state-changing comment
  attachments: [ {path, is_image} ],
  created_at
```

* Replies nest one level (Slack-thread style): a `parent_comment_id` always points at a top-level
  comment.
* **Yield comments** (`question`, `handoff`) render an action bar determined by the task's current
  cell (§1). A `question` with `options` renders the options as buttons; clicking one posts a
  reply whose body is the option text.
* **`AskUserQuestion` interception.** When a Claude thread calls `AskUserQuestion`, the harness
  handles the `can_use_tool` control request: it appends a `question` comment with the tool's
  options and moves the ball to the owner. The owner's answer is returned as the control response
  (`allow` with the answers in `updatedInput`), and the ball returns to the worker. To the agent
  it is an ordinary tool result; to the human it is an ordinary comment. *Assumption to verify
  during implementation:* the installed `claude` build emits `can_use_tool` for `AskUserQuestion`
  under `--input-format stream-json` and accepts answers in `updatedInput`; if not, the fallback
  is `yield --question --options`, which the meta skill instructs Claude threads to use instead.
* Providers without an equivalent tool use `yield --question --options`.
* Attachments: `is_image` renders inline. Agents attach screenshots and check output.

## 5. Subtasks

* Created by a worker (`harness task create`) → `owner = <creating thread_id>`,
  `parent_task_id = <its task>`, phase `todo`. `--start` dispatches immediately with the given
  preset; the subtask's primary thread is a child of the creating thread (lifecycle events flow as
  for any child thread).
* Same matrix, same verbs. The owning thread performs owner actions via the CLI
  (`task reply/proceed/approve/cancel <key>`) and is notified of the child's yields (§2.3).
* The human may act as owner on any subtask. The board shows *child waiting on its parent thread*
  muted and *waiting on the human* loud (§7).
* Cancelling or approving a parent does not touch children automatically, except **Cancel**, which
  cancels open children.
* Depth is unbounded by the schema; `delegating-subtasks` recommends one level.
* Human-created subtasks (owner = human) are ordinary tasks with a `parent_task_id`; the
  parent's handoff rule (§2.4) applies to them too.

## 6. Skills

### 6.1 Layout

```
harness/skills/
  using-harness/SKILL.md          # meta, always injected
  planning-a-task/SKILL.md        # phase: planning
  implementing-a-task/SKILL.md    # phase: implementing
  yielding/SKILL.md
  delegating-subtasks/SKILL.md
  test-driven-development/        # vendored from superpowers (MIT, attribution in LICENSES/)
  systematic-debugging/
  verification-before-completion/
  receiving-code-review/
  requesting-code-review/
  writing-skills/
```

`config.SKILLS_DIR` points here by default; a fork may point anywhere. Superpowers' process
skills (brainstorming, writing-plans, executing-plans, subagent-driven-development,
finishing-a-development-branch, using-git-worktrees, dispatching-parallel-agents) are **not**
vendored: their approval gates are ball flips here, and their artifacts (plan files, worktree
choice) are subtasks and presets.

### 6.2 Skill contract

Every phase and meta skill uses superpowers' enforcement skeleton: a one-line **Iron Law**, a
**hard gate**, a **rationalization table** (Thought → Reality), a **checklist**, and a flowchart
only at decision points. Descriptions state triggers, never workflow.

`using-harness` (< 150 words) states the Iron Laws:

1. You never end a turn on a task without `harness task yield` or `harness task proceed`.
2. Status is not yours to set; only yields, proceeds and owner actions move it.
3. Everything you tell a human is a comment; there is no other channel.
4. The phase skill in your system prompt is mandatory; read it before acting.

`planning-a-task`: understand the brief → decide: trivial and unambiguous → `proceed`; otherwise
ask (`yield --question`, batched, with options where possible), then produce a spec and
`yield --handoff`. Gate: no file edits in `planning` other than the spec.
`implementing-a-task`: REQUIRED SUB-SKILLS test-driven-development and
verification-before-completion; decompose into subtasks when work is independent
(`delegating-subtasks`); handoff body = what changed / how it was verified / where to look first.
`yielding`: a yield must be answerable by its owner in under thirty seconds; questions carry
options; handoffs carry evidence.

### 6.3 Delivery

* **System prompt** on every spawn *and* resume: `using-harness` + the phase skill for the task's
  current phase + the report-back contract (CLI usage, `$HARNESS_CLI`, task key, thread id) +
  preset instructions. Because phase can change between resumes, the system prompt is rebuilt on
  each `_spawn`.
* **In-turn phase change**: `harness task proceed` prints the `implementing-a-task` skill to
  stdout so the transition's tool result carries the new rules.
* **On-demand skills** (discipline tier) are exposed to the `Skill` tool by passing the skills
  directory as a local plugin (`--plugin-dir`). *Assumption to verify:* the installed `claude`
  supports `--plugin-dir`; fallback is a symlink into `~/.claude/skills` created by the harness at
  startup.

### 6.4 Testing skills

`tests/skills/` holds pressure scenarios (markdown prompt + fixture repo + expected verbs).
Runner: spawn a real thread with and without the skill under test (`tests/fake_claude.py` for the
cheap layers; a real `claude -p` behind `HARNESS_PAID_TESTS=1`). Assertions are mechanical: the
harness logs every CLI verb a thread calls, so "did it yield before ending?", "did it edit files
in planning?", "did it proceed without a spec under `plan_first`?" are checked facts, not
transcript reads. New or edited skills follow writing-skills' rule: baseline failure first.

## 7. UI

### 7.1 Board

Columns = phase: **Backlog · Todo · Planning · Implementing · Done**; Canceled behind a filter.
Card content: key, title, priority, and a cell indicator:

* `(…, owner)` with owner = human → highlighted "needs you" badge naming the flavor
  (question / spec ready / ready for review); these cards sort to the top of their column and are
  counted in the board header.
* `(…, owner)` with owner = thread → muted "waiting on parent" badge.
* `(…, worker)` → live activity (thread `live_status`, cost).
* Subtask count with how many are open.

### 7.2 Task tab

Top: key, title, description (editable while not started), preset picker, and the **Start**
button with an optional one-line prompt (phase ∈ {backlog, todo}); otherwise a cell chip
(e.g. "Planning · your turn") and the owner action bar for the current cell.
Middle: the comment stream, Slack-thread style; yield comments show their action bar; `question`
options render as buttons; `handoff` shows attachments and check output inline.
Composer: a comment box. Sending while ball = worker injects mid-turn (§2.1). `/call <preset>
[prompt]` attaches a new thread (§3.1). Reply boxes under each top-level comment.
Side: subtasks (with cells, click to open), threads (with live status, click for transcript).

### 7.3 Notifications

A "needs you" transition on any task owned by the human raises the harness notification (existing
`notify.py`), and the board header count updates.

## 8. Data

Additions to the existing JSON-persisted task store:

```
Task  += phase, ball, owner, primary_thread_id, parent_task_id, preset
Comment  (new table; schema in §4)
Thread += task_key (exists), verbs_log: [ {verb, args, ts, accepted, reason?} ]
```

`status` is removed; a one-time migration maps `backlog|todo → same`, `in_progress → (implementing,
worker)`, `in_review → (implementing, owner)`, `done|canceled → same`.

The state machine is a pure function `step(task, action) -> (task', comment)` in
`harness/lifecycle.py`; stores call it and persist both outputs. Rejections raise with the reason
string the CLI prints.

## 9. Testing

* `tests/test_lifecycle.py`: every cell × every action from §2 as a table, including rejections
  and the invariants in §2.4.
* `tests/test_cli.py` / `test_ipc.py`: each verb, ownership checks, `wait` semantics, auto-handoff
  on thread exit.
* `tests/test_ui_task.py` / `test_ui_board.py` (via `tests/ui.py`): action bars per cell, option
  buttons, "needs you" sorting and count, `/call`.
* `tests/skills/`: §6.4.

## 10. Out of scope

* What **Approve** does to the environment (merge, PR, worktree cleanup) — an Environments spec.
* Preset fields beyond `plan_first` and `instructions`.
* Multi-machine execution.

## Appendix — mapping from the earlier vocabulary

| Earlier idea | Here |
|---|---|
| TODO / InProgress / Validating / Complete | todo / (implementing, worker) / (implementing, owner) / done |
| Interrogation | (planning, owner) — and any `question` yield in either phase |
| receiver | primary thread |
| interrogator, implementors | any thread on the task; roles are emergent, not stored |
| "call in an agent from a comment" | `/call <preset>` |
| "subagent pings the original agent" | child thread lifecycle events + `task wait` |
