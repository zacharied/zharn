# Story lifecycle — implementation spec (2026-08-28, reworked 2026-08-30)

Implements the model in `docs/AGENT-MODEL.md`. That document defines *what* the program does and
why; this one fixes the mechanics: state representation, verbs, schemas, delivery, skills, UI,
migration, tests. Where code disagrees with either, the code is wrong.

## 1. State representation

```
Story.phase ∈ backlog | todo | planning | implementing | done | canceled
Story.ball    = derived: main_thread.turn while phase ∈ {planning, implementing}, else null
Story.author        = "human" | <character_id>
Story.protagonist   = <character_id> | null
Story.main_thread   = <thread_id> | null
Story.parent_story  = <story_key> | null

Thread    { id, story_key, author: "human"|<character_id>, lead: <character_id>,
            turn ∈ cast | author | resolved }
Character { id, story_key, role, name, live_context: <context_id>,
            forked_from: <character_id> | null,             # forked friends
            attention: <thread_id> | null,                  # thread of the last delivery
            inbox: [<comment_id>],                          # may hold sub-story comments
            recaps: [<comment_id>] }
Context   { id, owner: <character_id> | <minion of character_id> | "human",
            session_id, predecessor: <context_id> | null,   # recast lineage
            forked_from: <context_id> | null }              # forked friends (and minions)

Derived per character, never stored:
  owes    = threads it leads with turn = cast
  awaits  = threads it authored with turn = cast
          + sub-stories it authored with ball = cast
  status  = retired  (story terminal)
          | working  (live context mid-turn)
          | waiting  (stopped, awaits ≠ ∅)
          | idle     (stopped, awaits = ∅ — and then owes = ∅: the quiet check, §2.3)
```

`name` is the role name, suffixed `-2`, `-3` on collision; a fork is cast from its source's
role, so it collides by design ("Protagonist-2"). A **minion** is a native subagent (Claude's
`Agent` tool); harness-spawned minion contexts are out of scope (§9). A **fork** clones a context
(Claude: `--resume <session> --fork-session`). A **bare context** has `owner = "human"`, no
story, and an explore/read permission ceiling by default.

The state machine is a pure function `step(story, action) -> (story', comment)` in
`harness/lifecycle.py`; thread turns are part of its domain. Stores call it and persist both
outputs; rejections raise with the reason the CLI prints. Every phase-changing comment records
`transition: {from, to}`. `harness/threads.py` is renamed `harness/contexts.py`
(`Thread` → `Context`, `HARNESS_THREAD_ID` → `HARNESS_CONTEXT_ID`).

## 2. Transitions

### 2.1 Author actions (UI; CLI verbs when the author is a character)

| Action | Precondition | Effect |
|---|---|---|
| Start `[note] [role]` | phase ∈ {backlog, todo} | Open the main thread; the store casts the protagonist fresh from `role` (default `config.DEFAULT_ROLE`) with the brief (§3.1) and the Start comment names the role — the reducer sees only the protagonist's id; `note` is the root comment. → `(planning, cast)`. |
| Reply | some thread of the story has turn = author | Any author comment in such a thread **is** the reply to its one pending yield: append, deliver to the yield's author, turn → cast. On the main thread this moves the ball → `(same phase, cast)`. |
| Resolve `[note] --thread t` | `t`'s turn = author; not the main thread. (A thread still waiting on its cast cannot be resolved — a request is not retractable, only its answer is resolvable.) | `system` comment carrying the note; the pending yield is closed; the lead is neither resumed nor notified, and if it was attending `t` its attention clears; turn → resolved. No transition. |
| Proceed `[note]` | `(planning, author)` | System comment "outline approved" on main; resume protagonist. → `(implementing, cast)`. |
| Approve `[note]` | `(implementing, author)` | System comment; every open thread of the story resolves, main included; every character retires at its next turn boundary (§2.3). → `(done)`. |
| Back to planning `[note]` | `(implementing, author)` | System comment; resume protagonist with note. → `(planning, cast)`. |
| Cancel `[note]` | non-terminal | Stop every character's live context now (retired); cancel open sub-stories; every open thread resolves, main included. → `(canceled)`. |
| Reopen `note` | terminal | Resume the protagonist with `note` on main (the UI may offer a recast instead). → `(implementing, cast)`. |
| Open a thread `body` | started, non-terminal | Root comment. No mention → addressed to the protagonist; `@Name` → to Name; `/call <role> [note]` → cast a fresh friend to lead it; `/fork @Name [note]` → cast a friend forked from Name's live context to lead it. Lead = addressee; author = opener; delivered per §3.2. No transition. |
| Reply in a thread (turn = cast) | non-terminal | Delivered per §3.2 (attended → now; else inbox). No transition. |
| Recast `character [role] [model]` | — | At the character's next turn boundary (the author may Stop it to force one), replace `live_context` per the ladder (§3.4); system comment on main. Threads, inbox, pending yields, name survive. No transition. |
| New Context `[note]` | — | Bare context; not a story action. Promote (§6) casts it as a new story's protagonist. |

### 2.2 Cast actions — `zharn story …` inside a character

| Verb | Who | Precondition | Effect |
|---|---|---|---|
| `yield --question --body … [--options a,b] [--thread t]` | `t`'s lead (default `t` = attended thread) | thread has no pending yield | `question` comment; thread turn → author |
| `yield --handoff --body … [--attach …] [--thread t]` | `t`'s lead | as above; main thread in `implementing`: no open sub-stories, and the harness first runs each touched repo's `checks` in the story's environment for it (workspace spec §4.4), attaching `[{repo, cmd, exit, output}]` | `handoff` comment; thread turn → author |
| `resolve --thread t [--note …]` | `t`'s author | as §2.1 Resolve: turn = author, not the main thread | As §2.1 Resolve: system comment, yield closed, lead neither resumed nor notified, turn → resolved |
| `proceed [--note …]` | protagonist (main's lead) | `(planning, cast)`; if the role has `outline_first`, an outline handoff must have been Proceed-ed since the most recent entry into planning | System comment on main → `(implementing, cast)`. **stdout is the `implementing-a-story` skill.** |
| `recap --body … [--thread t]` | any | — | `recap` comment in `t` (default: attended thread, else main); recorded as the character's latest recap. No transition. |
| `comment --body … [--thread t] [--reply-to id] [--to @Name…] [--attach …]` | any | default `t` = attended thread | `text` comment, delivered per §3.2. No transition. |
| `call --role R [--as Name] [--fork] --note …` | any | — | Cast a friend: new thread authored by the caller, led by the friend, `note` as root. `--fork`: the friend's context is a clone of the caller's live context (`Character.forked_from` = caller). Prints id/name. A friend that should read another thread is told so in the note and comments there as a guest. |
| `wait` | any | `awaits ≠ ∅` | A guard, not a block: prints what the caller awaits (threads by lead, sub-stories) and "end your turn". Rejected when nothing is awaited: "you await nothing and owe #t — yield instead". The harness wakes the character with whatever arrives next (§2.3). |
| `create --title … [--description …] [--start --role R]` | any | — | Sub-story with `author = <this character>`, `parent_story = <this story>`. Its yields reach the character like any comment (§3.2); `wait` covers it. |
| `reply <key> --thread t --body …` · `resolve <key> --thread t [--note …]` · `proceed <key>` · `approve <key>` · `cancel <key>` · `recast <key> …` | author of `<key>` | — | Author actions of §2.1. Rejected otherwise. |
| `inbox` · `show [<key>]` · `list` · `cast [<key>]` | any | — | Read-only. |

There is no status verb of any kind. Rejections print the reason and exit non-zero; every verb
call (accepted or not) is appended to the character's `verbs_log`.

**Reopen rule.** On a non-terminal story a resolved thread is not locked: any comment in it
reopens it — turn → cast, delivered per §3.2 — and a yield in it (its "no pending yield"
precondition is already satisfied) reopens it straight to turn = author. On a terminal story
every thread is resolved and read-only: comments there are rejected — Reopen the story first.
Story **Reopen** therefore needs no special case: its note is a comment in the resolved main
thread of a now non-terminal story, which reopens to cast exactly as `(implementing, cast)`
requires.

### 2.3 Harness mechanics

**Delivery.** A comment addressed to a character (routing §3.2) lands by the target's status:

| Target is | In its attended thread | In any other thread |
|---|---|---|
| working | pushed to its context now; the model sees it at its next call within the same turn (verified under `--input-format stream-json`, 2026-08-31) | appended to its inbox |
| waiting or idle | pushed now; `attention` := that thread; the context is resumed, spawned, or — if unresumable — recast (§3.4) | same |

**At every turn end** — the process ending its turn, crashing, or being stopped by the human —
in this order:

1. `attention` clears if the character yielded or resolved there, or the thread was resolved.
2. **Quiet check.** If `awaits = ∅`, every owed thread with no pending yield gets a yield posted
   by the harness: `author = "system"`, `kind = handoff`, body = the last assistant text (or the
   error), `structured.auto_for = <character>`; turn → author. On main in `implementing` it
   carries the checks like any handoff. A reply to such a yield routes to the lead.
3. If the inbox is non-empty, the oldest item is popped: `attention` := its thread, delivered —
   a new turn. One item per turn.

| Trigger | Effect |
|---|---|
| Context passes `config.CONTEXT_WARN` (default 0.8) | Inject: "context low — post a `recap` in #<attended> now" |
| Context passes `config.CONTEXT_MAX`, or character unresumable when it must act | Auto-recast at the turn boundary per the ladder (§3.4); system comment says which rung |
| Sub-story's ball reaches author or terminal | The triggering comment is delivered to the author character like any other (cross-story) |
| Human acts as author on a character-owned sub-story | Applied; the resulting system comment is delivered to the owning character |
| Human types in a character's context view | Posted as a human comment in the character's attended thread (root comment addressed to it, if it attends nothing) |
| Story becomes terminal | Every character retires: Cancel stops each live context now; Approve lets a mid-turn context finish its turn (its verbs are already rejected). Nothing is delivered to a retired character; Reopen resumes the protagonist |

`AskUserQuestion` does not exist under `claude -p` (verified 2026-08-31); `yield --question
--options` is the only way to ask.

### 2.4 Invariants (asserted in tests)

* `Story.ball` = main thread's turn while planning/implementing; null otherwise. Never stored.
* Per thread: turn = author ⇔ exactly one pending yield in that thread; turn = resolved ⇒ no
  pending yield. (A stored `pending_yield` id is a denormalization of the comments, never truth.)
* The main thread is resolved ⇔ the story is terminal.
* Every thread has exactly one lead; every character has exactly one live context and attends at
  most one thread; a character's inbox never contains comments from its attended thread.
* Only a thread's lead yields in it (so only the protagonist on main); a main handoff is blocked
  while any sub-story is non-terminal; implementing-phase main handoffs always carry a check.
* A stopped character with `awaits = ∅` owes nothing (the quiet check, §2.3).
* The story is terminal ⇔ every character is retired.
* A forked friend's live context has `forked_from` = its source's live context at casting.
* Every phase transition has exactly one causing comment.
* "Needs you" = ball with author (flavor = the main pending yield's kind × phase: question /
  outline ready / ready for review) **plus** every thread authored by the human with turn =
  author. Threads and sub-stories authored by characters are the character's business.

## 3. Characters

### 3.1 Brief

Story key + title + description; the threads in order — resolved ones folded to root + yields +
closing note —
rendered as markdown with author names and kinds; each character's latest recap; sub-stories
with `(phase, ball)`; cast with roles; attachments; then the role's instructions and the call-in
note (or Start note). A recast context's brief ends with its situation: "you are a recast of
<name>; your predecessor's recap is above; you were attending #t; n items wait in your inbox;
you await …". A forked friend gets no brief — its context already holds everything — only the
call note and "you are a fork of <name>: you cannot change its plan; if the author's point must
reach it, `@<name>` it." The report-back contract is in the system prompt (§5.3), not the brief.

### 3.2 Routing and attention

Addressing: root comment, no mention → protagonist; root `@Name` → Name; `/call` → a fresh
friend; `/fork @Name` → a friend forked from Name. Reply while turn = author, by the author → the
pending yield's author (the lead, when the harness yielded); any other reply → the thread's lead;
`@Name` in any comment → also Name, as a guest who replies *in that thread*; never the comment's
own author. A sub-story's main-thread yield → the sub-story's author character. When it lands is
§2.3.

### 3.3 Context view

Per-context tab: thinking, tool calls, streamed text, cost, minions nested with their own
transcripts, and the recast lineage (predecessor contexts, read-only, stacked). Input box on
every context except minions': for a character it posts a comment (§2.3); for a bare context it
is plain conversation.

### 3.4 Recast ladder

New context = brief (§3.1, which includes recaps) + role instructions + phase skill. The recap
source, best first: **(1)** the character's latest `recap` comment if newer than
`config.RECAP_STALE_TURNS`; **(2)** else resume the outgoing context for one final turn that may
only `recap`; **(3)** else nothing — the brief alone (the old "unresumable" path, now the worst
rung). Recast applies to any character and may change role/model; it takes effect at a turn
boundary (a waiting character is at one already); old context becomes `predecessor`. The new
context's first message is the brief with its situation line (§3.1); then the ordinary delivery
loop continues — nothing bespoke.

## 4. Comments and threads

```
Comment
  id, story_key, thread_id,
  reply_to: comment_id | null,                    # null ⇔ root; replies nest one level
  author: "human" | <character_id> | "system",
  kind:   text | question | handoff | recap | system,
  body:   markdown,
  mentions: [character_id],
  structured: { options?: [str], answers?: [str],
                check?: {cmd, exit, output},
                transition?: {from: [phase, ball], to: [phase, ball]} },
  attachments: [ {path, is_image} ],
  created_at
```

* A thread whose turn = author renders the matching action bar (main thread: the story's cell
  actions; other threads: Reply · Resolve).
* `question.options` render as buttons; a click posts the reply.
* `is_image` attachments render inline.

## 5. Skills

### 5.1 Layout

```
harness/skills/
  being-a-character/       # meta, always injected (< 150 words)
  planning-a-story/        # phase: planning — classify, ask, outline, proceed
  implementing-a-story/    # phase: implementing — TDD, delegate, verify, hand off
  yielding/
  delegating/              # minion vs friend vs sub-story
  test-driven-development/ systematic-debugging/ verification-before-completion/
  receiving-code-review/ requesting-code-review/ writing-skills/     # vendored, MIT, LICENSES/superpowers
```

`config.SKILLS_DIR` defaults here. Not vendored: brainstorming, writing-plans, executing-plans,
subagent-driven-development, finishing-a-development-branch, using-git-worktrees,
dispatching-parallel-agents — their gates are turn flips and their artifacts are comments,
friends, minions and sub-stories.

### 5.2 Contract

Phase/meta skills use superpowers' skeleton (Iron Law, hard gate, rationalization table,
checklist, flowchart only at decision points; descriptions are triggers, never workflow).

`being-a-character` iron laws: (1) never stop while you owe a thread unless a friend or a
sub-story is out — the harness will yield for you and say so; (2) status is not
yours to set; (3) everything you say to a human is a comment; (4) the phase skill in your system
prompt is mandatory; (5) when told your context is low, `recap` before anything else.
`planning-a-story`: classify (spike / bounded / needs outline) → bounded: `proceed`; spike:
minions, then `yield --handoff` with the answer; outline: batched questions → outline →
`yield --handoff`. Gate: no edits outside the outline while planning.
`implementing-a-story`: REQUIRED test-driven-development, verification-before-completion,
delegating; protect your context — minions read, friends build, you hold the plot; handoff body
= what changed / how verified / where to look first.
`delegating`: the §6 table of AGENT-MODEL.md, plus: friends for reviews always.
`yielding`: answerable in thirty seconds; questions carry options; handoffs carry evidence.

### 5.3 Delivery

* System prompt, rebuilt on every spawn, resume, *and recast*: `being-a-character` + phase skill
  + contract (CLI usage, `$HARNESS_CLI`, story key, character name/id, attended thread) + role
  instructions.
* In-turn phase change: `proceed` prints `implementing-a-story` to stdout.
* Skills via `--plugin-dir <SKILLS_DIR>`: `harness/skills/` is one plugin
  (`.claude-plugin/plugin.json` + `skills/*/SKILL.md`; verified 2026-08-31).

### 5.4 Testing

`tests/skills/<scenario>/` = prompt + fixture repo + expected verbs. Runner spawns a character
with and without the skill (`tests/fake_claude.py` for cheap layers; real `claude -p` behind
`HARNESS_PAID_TESTS=1`). Assertions read `verbs_log`, not transcripts. New/edited skills:
baseline failure first (writing-skills).

## 6. UI

* **Board** (`qml/content/StoryBoard.qml`): columns Backlog · Todo · Planning · Implementing ·
  Done; Canceled behind a filter. Card: key, title, priority, needs-you badge with flavor
  (§2.4, includes waiting side threads; sorted first, counted in header) / waiting-on-character
  muted / live activity, cast avatars with attention state, open sub-story count.
* **Story tab** (`qml/content/Story.qml`): header (key, title, editable description while
  unstarted, role picker + Start with note | phase chip + main action bar); threads with
  replies, option buttons, handoff evidence, resolved threads folded to root + yields + closing
  note; a composer per thread and
  one for new threads, `@` autocomplete over the cast, `/call <role> [note]` and
  `/fork @Name [note]`; side panel: cast (status: working on #n / waiting / idle / retired ·
  forked from · inbox depth · context meter · Recast button → role/model dialog), sub-stories
  (phase+ball → open).
* **Contexts** (`qml/content/Contexts.qml` + `ContextView.qml`): list of all contexts —
  characters' with recast lineage, bare, minions under dispatcher — and **New Context**. Views
  per §3.3. Bare contexts carry **Promote to story**: dialog (title, description) → story in
  `planning` with this context cast as protagonist; brief injected on promote.
* **Notifications**: needs-you transitions on human-authored stories and threads raise
  `notify.py`.

## 7. Data and migration

> **Compatibility policy (2026-08-31, DESIGN.md §0): no migration is built.** The old
> `.harness/` store is deleted, not converted; `Thread` → `Context` is a rename with no alias.
> The paragraph below is kept as the *vocabulary map* between old and new records only.


Existing JSON store. `Task` → `Story` (`key, title, description, priority, phase, author,
protagonist, main_thread, parent_story, role`; **ball not stored**); `Thread` (comments) and
`Comment` new (§1, §4); code `Thread` → `Context` (+ `owner, predecessor, forked_from`);
`Character` new (+ `verbs_log`). Migration: `backlog|todo|done|canceled → same`,
`in_progress → implementing, main.turn = cast`, `in_review → implementing, main.turn = author`;
each existing top-level comment becomes a thread; existing agent threads on a task become
characters named after their preset, the earliest the protagonist, their contexts carried over.
Presets are renamed roles (`harness/presets.py` → `harness/roles.py`), gaining
`outline_first: bool`. On-disk layout (`.zharn/stories/<key>/`, `local/`) and the `.harness/` →
`.zharn/` move are in the workspace spec (`2026-08-31-workspace-model-design.md` §6, §9).

## 8. Tests

* `tests/test_lifecycle.py`: every cell × every action of §2 as a table, per-thread turn flips,
  rejections, §2.4 invariants. Resolve: rejections (main thread, turn = cast, non-author,
  terminal story), reopen-on-comment and reopen-on-yield, the Approve/Cancel terminal sweep,
  needs-you dropping resolved threads.
* `tests/test_cli.py`, `test_ipc.py`, `test_stories.py`: each verb, lead/author checks, `wait`
  as a guard, delivery by status (attended push vs inbox, one pop per turn, attention moves),
  the quiet check at turn end (normal end, crash, Stop), retirement on Approve/Cancel,
  `call --fork` and `/fork`, recap in the attended thread, recast ladder rungs 1–3 with the
  situation line, cross-story sub-story delivery.
* `tests/test_ui_story.py`, `test_ui_board.py`, `test_ui_contexts.py` via `tests/ui.py`: action
  bars per cell and per waiting thread, option buttons, needs-you sort/count, `@` and `/call`,
  context-view input posting comments, New Context, Promote.
* `tests/skills/`: §5.4.

## 9. Out of scope

Approve's effect on the environment (merge/PR/worktree); workspaces, repos and environments
themselves (own spec, 2026-08-31); roles beyond `outline_first` and `instructions`; multi-machine
execution; harness-spawned minions (`minion`, `minion --fork` — Claude's native `Agent` tool
serves for now); a mechanical cap on guest mention loops; provider-side compaction (recast
supersedes it).

## Appendix — vocabulary map

| Earlier | Now |
|---|---|
| Task / subtask | Story / sub-story |
| bb thread · code `Thread` · "agent conversation" | context (`harness/contexts.py`) |
| bb "new thread" | New Context (bare), or casting a character |
| preset | role |
| primary thread / receiver | protagonist |
| thread on a task | character (friend) |
| native subagent, hidden helper thread | minion |
| owner | author |
| top-level comment + replies | thread |
| ball = worker | ball = cast (= main thread's turn) |
| transcript tab (read-only) | context view (interactive; minions read-only) |
| provider compaction / lost session | recap + recast |
| TODO / InProgress / Validating / Complete | todo / (implementing, cast) / (implementing, author) / done |
| Interrogation | (planning, author), or any question yield |
