# Story lifecycle — implementation spec (2026-08-28)

Implements the model in `docs/AGENT-MODEL.md`. That document defines *what* the program does and
why; this one fixes the mechanics: state representation, verbs, schemas, delivery of skills,
UI components, migration, tests. Where code disagrees with either, the code is wrong.

## 1. State representation

```
Story.phase ∈ backlog | todo | planning | implementing | done | canceled
Story.ball  ∈ cast | author | null      # null iff phase ∈ {backlog, todo, done, canceled}
Story.author        = "human" | <character_id>
Story.protagonist   = <character_id> | null
Story.parent_story  = <story_key> | null
```

A **character** is a thread (`harness/threads.py`) plus `{story_key, role, name}`. `name` is the
role name, suffixed `-2`, `-3` on collision. A **minion** is either a native subagent (Claude's
`Agent` tool) or a hidden thread with `{dispatcher: <character_id>}` and no `name`; minions never
appear in comments and are listed only under their dispatcher's transcript.

The state machine is a pure function `step(story, action) -> (story', comment)` in
`harness/lifecycle.py`. Stores call it and persist both outputs; rejections raise with the reason
the CLI prints. Every state-changing comment records `transition: {from, to}`.

## 2. Transitions

### 2.1 Author actions (UI buttons; CLI verbs when the author is a character)

| Action | Precondition | Effect |
|---|---|---|
| Start `[note] [role]` | phase ∈ {backlog, todo} | Cast the protagonist from `role` (default `config.DEFAULT_ROLE`) with the brief (§3.1); `note` becomes comment #1 and the first user message. → `(planning, cast)`. |
| Reply to a yield | ball = author | Append reply; resume the authoring character with it. → `(same phase, cast)`. |
| Proceed `[note]` | `(planning, author)` | System comment "outline approved"; resume protagonist. → `(implementing, cast)`. |
| Approve `[note]` | `(implementing, author)` | System comment; nobody resumed. → `(done, null)`. |
| Back to planning `[note]` | `(implementing, author)` | System comment; resume protagonist with note. → `(planning, cast)`. |
| Cancel `[note]` | non-terminal | Stop every character and minion; cancel open sub-stories. → `(canceled, null)`. |
| Reopen `note` | terminal | Resume (or recast) protagonist with note. → `(implementing, cast)`. |
| Comment | ball = cast | Deliver to target character (§3.2) as a mid-turn user message. **No transition.** |
| Call in a friend `role [note]` | non-terminal | Cast a character; system comment records it; the friend receives the brief + `note`. No transition. |

### 2.2 Cast actions — `harness story …` inside a character

| Verb | Who | Precondition | Effect |
|---|---|---|---|
| `yield --question --body … [--options a,b]` | any | ball = cast | `question` comment → `(same, author)` |
| `yield --handoff --body … [--attach …]` | protagonist | ball = cast; no open sub-stories | `handoff` comment; in `implementing` the harness runs `config.CHECK_CMD` first and attaches `{cmd, exit, output}` → `(same, author)` |
| `proceed [--note …]` | protagonist | `(planning, cast)`; if the story's role has `outline_first`, an outline handoff must have been Proceed-ed | System comment → `(implementing, cast)`. **stdout is the `implementing-a-story` skill.** |
| `comment --body … [--reply-to id] [--to @Name…] [--attach …]` | any | — | `text` comment; each `@Name` is delivered to that character (resume if idle). No transition. |
| `call --role R [--as Name] --note …` | any | — | Cast a friend (child thread of caller). Prints the character id/name. |
| `wait @Name [--timeout s]` | any | — | Block until that character posts its next comment or ends; print the comment. |
| `minion --role R --prompt … [--n k]` | any | — | Spawn hidden thread(s) under the caller; block; print result(s). Characters on Claude may use the native `Agent` tool instead. |
| `create --title … [--description …] [--start --role R]` | any | — | Sub-story with `author = <this character>`, `parent_story = <this story>`. |
| `wait <key>` | author of `<key>` | — | Block until `<key>` reaches `(…, author)` or terminal; print the triggering comment. |
| `reply <key> --comment id --body …` · `proceed <key>` · `approve <key>` · `cancel <key>` | author of `<key>` | — | Author actions of §2.1. Rejected otherwise. |
| `show [<key>]` · `list` · `cast [<key>]` | any | — | Read-only. |

There is no status verb of any kind. Rejections print the reason and exit non-zero; every verb
call (accepted or not) is appended to the character's `verbs_log`.

### 2.3 Harness-driven transitions

| Trigger | Effect |
|---|---|
| Last running character on a story exits while ball = cast | System comment "cast went quiet without a handoff" + last assistant text → `(same phase, author)` |
| Sub-story reaches `(…, author)` or terminal | Author character notified: `wait` returns, or the character is resumed with the comment |
| Human acts as author on a sub-story owned by a character | Applied; owning character notified with the resulting system comment |
| Protagonist unresumable when it must act | Recast: new thread from the same role with the full brief; system comment; `Story.protagonist` updated |
| `@Name` in a human comment | Resume that character with the comment; no transition |

### 2.4 Invariants (asserted in tests)

* `ball is null` ⇔ terminal-or-unstarted phase.
* No pending yield while ball = cast; exactly one pending yield while ball = author.
* "Needs you" flavor = the pending yield's kind × phase: question / outline ready (planning
  handoff) / ready for review (implementing handoff).
* Protagonist cannot hand off with a non-terminal sub-story.
* Every transition has exactly one causing comment.

## 3. Characters

### 3.1 Brief

Story key + title + description; the comment stream in order, rendered as markdown with author
names and kinds; sub-stories with `(phase, ball)`; cast with roles; attachments; then the role's
instructions and the call-in note (or Start note). The report-back contract is in the system
prompt (§5.3), not the brief.

### 3.2 Routing

Reply → the character that authored the parent (top-level) comment. Top-level, no mention →
protagonist. `@Name` → that character. Idle target → resume its session; unresumable → recast
(§2.3, protagonist) or system comment "Name is gone" (friend).

### 3.3 Transcript

Per-character read-only tab: thinking, tool calls, streamed text, cost, and a nested list of its
minions with their transcripts. No input box.

## 4. Comments

```
Comment
  id, story_key, parent_comment_id | null,           # replies nest one level
  author: "human" | <character_id> | "system",
  kind:   text | question | handoff | system,
  body:   markdown,
  mentions: [character_id],
  structured: { options?: [str], answers?: [str],
                check?: {cmd, exit, output},
                transition?: {from: [phase, ball], to: [phase, ball]} },
  attachments: [ {path, is_image} ],
  created_at
```

* Yield comments render the author action bar for the story's current cell.
* `question.options` render as buttons; a click posts a reply whose body is the option text.
* **`AskUserQuestion` interception**: on the `can_use_tool` control request the harness appends a
  `question` comment, moves the ball to the author, and answers the request with the author's
  choice in `updatedInput`. *Assumption to verify:* the installed `claude` emits `can_use_tool`
  for `AskUserQuestion` under `--input-format stream-json`; fallback is `yield --question
  --options`, which the meta skill tells Claude characters to use.
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
dispatching-parallel-agents — their gates are ball flips and their artifacts are comments,
friends, minions and sub-stories.

### 5.2 Contract

Phase/meta skills use superpowers' skeleton (Iron Law, hard gate, rationalization table,
checklist, flowchart only at decision points; descriptions are triggers, never workflow).

`being-a-character` iron laws: (1) never end a turn on a story without `yield`, `proceed`, or a
`wait` that is still pending; (2) status is not yours to set; (3) everything you say to a human
is a comment; (4) the phase skill in your system prompt is mandatory.
`planning-a-story`: classify (spike / bounded / needs outline) → bounded: `proceed`; spike:
minions, then `yield --handoff` with the answer; outline: batched questions → outline →
`yield --handoff`. Gate: no edits outside the outline while planning.
`implementing-a-story`: REQUIRED test-driven-development, verification-before-completion,
delegating; handoff body = what changed / how verified / where to look first.
`delegating`: the §6 table of AGENT-MODEL.md, plus: friends for reviews always.
`yielding`: answerable in thirty seconds; questions carry options; handoffs carry evidence.

### 5.3 Delivery

* System prompt, rebuilt on every spawn *and* resume: `being-a-character` + phase skill + contract
  (CLI usage, `$HARNESS_CLI`, story key, character name/id) + role instructions.
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
  Done; Canceled behind a filter. Card: key, title, priority, cell indicator (needs-you badge with
  flavor, sorted first, counted in header / waiting-on-character muted / live activity), cast
  avatars with live status, open sub-story count.
* **Story tab** (`qml/content/Story.qml`): header (key, title, editable description while
  unstarted, role picker + Start with optional note | cell chip + author action bar); comment
  stream with threaded replies, option buttons, handoff evidence; composer with `@` autocomplete
  over the cast and `/call <role> [note]`; side panel: cast (live status → transcript tab),
  sub-stories (cell → open).
* **Notifications**: needs-you transitions on human-authored stories raise `notify.py`.

## 7. Data and migration

Existing JSON store. `Task` → `Story` (`key, title, description, priority, phase, ball, author,
protagonist, parent_story, role`); `Comment` new (§4); `Thread += story_key, role, name,
dispatcher, verbs_log`. Migration: `backlog|todo|done|canceled → same`,
`in_progress → (implementing, cast)`, `in_review → (implementing, author)`; existing threads on
a task become characters named after their preset; the earliest is the protagonist. Presets are
renamed roles (`harness/presets.py` → `harness/roles.py`), gaining `outline_first: bool`.

## 8. Tests

* `tests/test_lifecycle.py`: every cell × every action of §2 as a table, rejections, §2.4
  invariants.
* `tests/test_cli.py`, `test_ipc.py`: each verb, authorship checks, `wait` semantics,
  auto-yield on exit, recast.
* `tests/test_ui_story.py`, `test_ui_board.py` via `tests/ui.py`: action bars per cell, option
  buttons, needs-you sort/count, `@` and `/call`.
* `tests/skills/`: §5.4.

## 9. Out of scope

Approve's effect on the environment (merge/PR/worktree); roles beyond `outline_first` and
`instructions`; multi-machine execution.

## Appendix — vocabulary map

| Earlier | Now |
|---|---|
| Task / subtask | Story / sub-story |
| preset | role |
| primary thread / receiver | protagonist |
| thread on a task | character (friend) |
| native subagent, hidden helper thread | minion |
| owner | author |
| ball = worker | ball = cast |
| TODO / InProgress / Validating / Complete | todo / (implementing, cast) / (implementing, author) / done |
| Interrogation | (planning, author), or any question yield |
