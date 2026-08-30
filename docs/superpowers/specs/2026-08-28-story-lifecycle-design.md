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
            turn ∈ cast | author }
Character { id, story_key, role, name, live_context: <context_id>,
            attention: <thread_id> | null, inbox: [<comment_id>] }
Context   { id, owner: <character_id> | <minion of character_id> | "human",
            session_id, predecessor: <context_id> | null,   # recast lineage
            forked_from: <context_id> | null }              # minions only
```

`name` is the role name, suffixed `-2`, `-3` on collision. A **minion** is either a native
subagent (Claude's `Agent` tool) or a hidden context with no character; `--fork` clones the
dispatcher's context (Claude: `--resume <session> --fork-session`). A **bare context** has
`owner = "human"`, no story, and an explore/read permission ceiling by default.

The state machine is a pure function `step(story, action) -> (story', comment)` in
`harness/lifecycle.py`; thread turns are part of its domain. Stores call it and persist both
outputs; rejections raise with the reason the CLI prints. Every phase-changing comment records
`transition: {from, to}`. `harness/threads.py` is renamed `harness/contexts.py`
(`Thread` → `Context`, `HARNESS_THREAD_ID` → `HARNESS_CONTEXT_ID`).

## 2. Transitions

### 2.1 Author actions (UI; CLI verbs when the author is a character)

| Action | Precondition | Effect |
|---|---|---|
| Start `[note] [role]` | phase ∈ {backlog, todo} | Open the main thread; cast the protagonist fresh from `role` (default `config.DEFAULT_ROLE`) with the brief (§3.1); `note` is the root comment. → `(planning, cast)`. |
| Reply | some thread of the story has turn = author | Any author comment in such a thread **is** the reply to its one pending yield: append, deliver to the yield's author, turn → cast. On the main thread this moves the ball → `(same phase, cast)`. |
| Proceed `[note]` | `(planning, author)` | System comment "outline approved" on main; resume protagonist. → `(implementing, cast)`. |
| Approve `[note]` | `(implementing, author)` | System comment; nobody resumed. → `(done)`. |
| Back to planning `[note]` | `(implementing, author)` | System comment; resume protagonist with note. → `(planning, cast)`. |
| Cancel `[note]` | non-terminal | Stop every character and minion; cancel open sub-stories. → `(canceled)`. |
| Reopen `note` | terminal | Resume (or recast) protagonist with note on main. → `(implementing, cast)`. |
| Open a thread `body` | started, non-terminal | Root comment. No mention → addressed to the protagonist; `@Name` → to Name; `/call <role> [note]` → cast a fresh friend to lead it. Lead = addressee; author = opener; delivered per §3.2. No transition. |
| Reply in a thread (turn = cast) | — | Delivered per §3.2 (attended → now; else inbox). No transition. |
| Recast `character [role] [model]` | character not mid-turn (author may stop it first) | Replace `live_context` per the ladder (§3.4); system comment on main. Threads, inbox, pending yields, name survive. No transition. |
| New Context `[note]` | — | Bare context; not a story action. Promote (§6) casts it as a new story's protagonist. |

### 2.2 Cast actions — `zharn story …` inside a character

| Verb | Who | Precondition | Effect |
|---|---|---|---|
| `yield --question --body … [--options a,b] [--thread t]` | engaged character | thread has no pending yield; main thread: protagonist only | `question` comment; thread turn → author |
| `yield --handoff --body … [--attach …] [--thread t]` | engaged character | as above; main thread in `implementing`: no open sub-stories, and the harness runs `config.CHECK_CMD` first, attaching `{cmd, exit, output}` | `handoff` comment; thread turn → author |
| `proceed [--note …]` | protagonist | `(planning, cast)`; if the role has `outline_first`, an outline handoff must have been Proceed-ed | System comment on main → `(implementing, cast)`. **stdout is the `implementing-a-story` skill.** |
| `recap --body …` | any | — | `recap` comment on main; recorded as the character's latest recap. No transition. |
| `comment --body … [--thread t] [--reply-to id] [--to @Name…] [--attach …]` | any | default `t` = attended thread | `text` comment, delivered per §3.2. No transition. |
| `call --role R [--as Name] [--in t] --note …` | any | — | Cast a fresh friend. Default: new thread authored by caller, led by the friend, `note` as root. `--in t`: call-in posted as a reply in `t`; the friend joins `t` (lead unchanged). Prints id/name. |
| `wait @Name [--timeout s]` | any | — | Block until Name yields in a thread authored by the caller (incl. harness auto-yield), or until interrupted per §3.2; print what arrived and why. |
| `minion --role R --prompt … [--n k] [--fork]` | any | — | Hidden context(s); `--fork` clones the caller's context. Block; print result(s). Claude characters may use the native `Agent` tool instead. |
| `create --title … [--description …] [--start --role R]` | any | — | Sub-story with `author = <this character>`, `parent_story = <this story>`. |
| `wait <key>` | author of `<key>` | — | Block until `<key>`'s ball reaches author or terminal; print the triggering comment. |
| `reply <key> --thread t --body …` · `proceed <key>` · `approve <key>` · `cancel <key>` · `recast <key> …` | author of `<key>` | — | Author actions of §2.1. Rejected otherwise. |
| `inbox` · `show [<key>]` · `list` · `cast [<key>]` | any | — | Read-only. |

There is no status verb of any kind. Rejections print the reason and exit non-zero; every verb
call (accepted or not) is appended to the character's `verbs_log`.

### 2.3 Harness mechanics

| Trigger | Effect |
|---|---|
| Comment addressed to a character (routing §3.2) in its **attended** thread | Delivered now: queued as the next user message mid-turn; a blocked `wait` returns early, labeled "interrupted by reply in #t" |
| Comment addressed to a character in any **other** thread | Appended to its inbox; when the character is waiting or idle, the oldest item is delivered and `attention` moves to that thread, with a note naming any wait it displaced |
| Lead ends its turn in its attended thread with no pending yield and no pending wait | Harness posts a yield "went quiet" (+ last assistant text) in that thread; turn → author |
| Context passes `config.CONTEXT_WARN` (default 0.8) | Inject: "context low — post a `recap` on the main thread now" |
| Context passes `config.CONTEXT_MAX`, or character unresumable when it must act | Auto-recast at the turn boundary per the ladder (§3.4); system comment says which rung |
| Sub-story's ball reaches author or terminal | Author character notified: `wait <key>` returns, or delivery per its attention |
| Human acts as author on a character-owned sub-story | Applied; owning character notified with the resulting system comment |
| Human types in a character's context view | Posted as a human comment in the character's attended thread (root comment addressed to it, if it attends nothing) |
| `AskUserQuestion` from a character | Intercepted via `can_use_tool`: posted as a `question` yield in the attended thread; the author's choice answers the request in `updatedInput`. *Assumption to verify* under `--input-format stream-json`; fallback is `yield --question --options`. |

### 2.4 Invariants (asserted in tests)

* `Story.ball` = main thread's turn while planning/implementing; null otherwise. Never stored.
* Per thread: turn = author ⇔ exactly one pending yield in that thread.
* Every thread has exactly one lead; every character has exactly one live context and attends at
  most one thread; a character's inbox never contains comments from its attended thread.
* Only the protagonist yields on the main thread; a main handoff is blocked while any sub-story
  is non-terminal; implementing-phase main handoffs always carry a check.
* Every phase transition has exactly one causing comment.
* "Needs you" = ball with author (flavor = the main pending yield's kind × phase: question /
  outline ready / ready for review) **plus** every thread authored by the human with turn =
  author. Threads and sub-stories authored by characters are the character's business.

## 3. Characters

### 3.1 Brief

Story key + title + description; the threads in order — resolved ones folded to root + yields —
rendered as markdown with author names and kinds; recaps; sub-stories with `(phase, ball)`; cast
with roles; attachments; then the role's instructions and the call-in note (or Start note).
A recast context's brief ends with "you are a recast of <name>; your predecessor's recap is
above." The report-back contract is in the system prompt (§5.3), not the brief.

### 3.2 Routing and attention

Addressing: root comment, no mention → protagonist; root `@Name` → Name; `/call` → new fresh
friend. Reply, no mention → the thread's lead; reply to a yield → the yield's author; `@Name` in
any comment → also delivered to Name, who replies *in that thread*. Delivery per §2.3: attended
thread now, otherwise inbox. Idle target → resume its context; unresumable → recast (§3.4).

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
boundary; old context becomes `predecessor`.

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
  actions; other threads: Reply).
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

`being-a-character` iron laws: (1) never leave a thread you are attending without a yield, a
reply, or a wait still pending — the harness will yield for you and say so; (2) status is not
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
* Discipline skills via `--plugin-dir <SKILLS_DIR>`. *Assumption to verify*; fallback: symlink
  into `~/.claude/skills` at harness start.

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
  replies, option buttons, handoff evidence, resolved threads folded; a composer per thread and
  one for new threads, `@` autocomplete over the cast and `/call <role> [note]`; side panel:
  cast (attention: busy on #n / waiting / idle · inbox depth · context meter · Recast button →
  role/model dialog), sub-stories (phase+ball → open).
* **Contexts** (`qml/content/Contexts.qml` + `ContextView.qml`): list of all contexts —
  characters' with recast lineage, bare, minions under dispatcher — and **New Context**. Views
  per §3.3. Bare contexts carry **Promote to story**: dialog (title, description) → story in
  `planning` with this context cast as protagonist; brief injected on promote.
* **Notifications**: needs-you transitions on human-authored stories and threads raise
  `notify.py`.

## 7. Data and migration

Existing JSON store. `Task` → `Story` (`key, title, description, priority, phase, author,
protagonist, main_thread, parent_story, role`; **ball not stored**); `Thread` (comments) and
`Comment` new (§1, §4); code `Thread` → `Context` (+ `owner, predecessor, forked_from`);
`Character` new (+ `verbs_log`). Migration: `backlog|todo|done|canceled → same`,
`in_progress → implementing, main.turn = cast`, `in_review → implementing, main.turn = author`;
each existing top-level comment becomes a thread; existing agent threads on a task become
characters named after their preset, the earliest the protagonist, their contexts carried over.
Presets are renamed roles (`harness/presets.py` → `harness/roles.py`), gaining
`outline_first: bool`.

## 8. Tests

* `tests/test_lifecycle.py`: every cell × every action of §2 as a table, per-thread turn flips,
  rejections, §2.4 invariants.
* `tests/test_cli.py`, `test_ipc.py`: each verb, authorship checks, `wait` semantics including
  interruption labels, inbox ordering and attention moves, per-thread auto-yield, recap, recast
  ladder rungs 1–3, sub-story flows.
* `tests/test_ui_story.py`, `test_ui_board.py`, `test_ui_contexts.py` via `tests/ui.py`: action
  bars per cell and per waiting thread, option buttons, needs-you sort/count, `@` and `/call`,
  context-view input posting comments, New Context, Promote.
* `tests/skills/`: §5.4.

## 9. Out of scope

Approve's effect on the environment (merge/PR/worktree); roles beyond `outline_first` and
`instructions`; multi-machine execution; context forking beyond `minion --fork`; provider-side
compaction (recast supersedes it).

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
