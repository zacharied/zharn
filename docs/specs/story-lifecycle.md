# Story lifecycle

Implements the model in [`docs/AGENT-MODEL.md`](../AGENT-MODEL.md). That document defines *what*
the program does and why; this one fixes the mechanics: state representation, verbs, schemas,
delivery, skills, UI, tests. Where code disagrees with either, the code is wrong.

*Written 2026-08-28; reworked 2026-08-30.*

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
            recaps: [<comment_id>],
            context_warned: <int> | absent,                 # recaps it had when its context crossed CONTEXT_WARN (§2.3)
            context_maxed: true | absent,                   # its context crossed CONTEXT_MAX; a recast is pending (§3.4)
            phase_seen: <phase> | null }                    # the phase whose skill it last received (§5.3)
Context   { id, owner: <character_id> | <minion of character_id> | "human",
            session_id, predecessor: <context_id> | null,   # recast lineage
            forked_from: <context_id> | null,               # forked friends, asides (and minions)
            about: {story_key, comment_id} | null }         # asides: the pinned comment

Derived per context, never stored:
  reading = input_tokens + cache_read_input_tokens + cache_creation_input_tokens of its latest assistant
            event: what the context holds. A fork starts with its source's reading.
  window  = the model's context window, from the latest result's modelUsage; unknown until the first

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
`Agent` tool); harness-spawned minion contexts are out of scope (§8). A **fork** clones a context
(Claude: `--resume <session> --fork-session`). A **bare context** has `owner = "human"`, no
story, and an explore/read permission ceiling by default.

The state machine is a pure function `step(story, action) -> (story', comment)` in
`harness/lifecycle.py`; thread turns are part of its domain. Stores call it and persist both
outputs; rejections raise with the reason the CLI prints. Every phase-changing comment records
`transition: {from, to}`.

## 2. Transitions

### 2.1 Author actions (UI; CLI verbs when the author is a character)

| Action | Precondition | Effect |
|---|---|---|
| Start `[note] [role]` | phase ∈ {backlog, todo} | Open the main thread; the store casts the protagonist fresh from `role` (default `config.DEFAULT_ROLE`) with the brief (§3.1) and the Start comment names the role — the reducer sees only the protagonist's id; `note` is the root comment. → `(planning, cast)`. |
| Reply | some thread of the story has turn = author | Any author comment in such a thread **is** the reply to its one pending yield: append, deliver to the yield's author, turn → cast. On the main thread this moves the ball → `(same phase, cast)`. |
| Resolve `[note] --thread t` | `t`'s turn = author; not the main thread. (A thread still waiting on its cast cannot be resolved — a request is not retractable, only its answer is resolvable.) | `system` comment carrying the note; the pending yield is closed; the lead is neither resumed nor notified, and if it was attending `t` its attention clears; turn → resolved. No transition. |
| Proceed `[note]` | `(planning, author)` | System comment "outline approved" on main; resume protagonist. → `(implementing, cast)`. |
| Approve `[note]` | `(implementing, author)`, and every environment of the story fast-forwards into its target ([workspace spec](workspace-model.md) §4.8) | Each environment's target is moved onto the story branch's tip; system comment carrying what landed (`structured.merged`); every open thread of the story resolves, main included; every character retires at its next turn boundary (§2.3); worktrees are removed as the cast retires. → `(done)`. |
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
| `yield --question [--thread t]` — a JSON document on stdin: `{body?, questions: [{text, options?, default?}]}` | `t`'s lead (default `t` = attended thread) | thread has no pending yield; at least one question, each with non-empty `text`, `options` a list of strings (absent or empty: free text), `default` a string. Invalid JSON is refused by the CLI; a wrong shape by the store | `question` comment, `structured.questions` normalized (`options` always a list, `default` only when given); thread turn → author |
| `yield --handoff --body … [--despite-checks] [--thread t]` | `t`'s lead | as above; main thread in `implementing`: no open sub-stories, every environment of the story has a clean tree and a branch up to date with its target (no flag past either), then each repo's `checks` run in its environment, attaching `[{repo, cmd, exit, output}]` ([workspace spec](workspace-model.md) §4.6) | `handoff` comment; thread turn → author |
| `resolve --thread t [--note …]` | `t`'s author | as §2.1 Resolve: turn = author, not the main thread | As §2.1 Resolve: system comment, yield closed, lead neither resumed nor notified, turn → resolved |
| `proceed [--note …]` | protagonist (main's lead) | `(planning, cast)`; if the role has `outline_first`, an outline handoff must have been Proceed-ed since the most recent entry into planning | System comment on main → `(implementing, cast)`. **stdout is the `implementing-a-story` skill**; `phase_seen` := implementing. |
| `recap --body … [--thread t]` | any | — | `recap` comment in `t` (default: attended thread, else main); recorded as the character's latest recap. No transition. |
| `comment --body … [--thread t] [--reply-to id] [--to @Name…] [--attach …]` | any | default `t` = attended thread | `text` comment, delivered per §3.2. No transition. |
| `call --role R [--as Name] [--fork] --note …` | any | — | Cast a friend: new thread authored by the caller, led by the friend, `note` as root. `--fork`: the friend's context is a clone of the caller's live context (`Character.forked_from` = caller). Prints id/name. A friend that should read another thread is told so in the note and comments there as a guest. |
| `wait` | any | not (`awaits = ∅` and `owes ≠ ∅`) | A guard, not a block: prints what the caller awaits (threads by lead, sub-stories) and "end your turn"; with nothing awaited and nothing owed it says so and that a reply will wake it. Rejected only in the one state where stopping would go quiet: "you await nothing and owe #t — yield instead". The harness wakes the character with whatever arrives next (§2.3). |
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
| Reading passes `config.CONTEXT_WARN` mid-turn (300K tokens for a 1M window; a smaller window scales it) | Once per context: push `[harness] context past the warn line: post a `recap` in #<attended> now — your successor is built from the story record and that recap.`; the situation line ends `· recap due` until a recap lands (§5.3) |
| Reading passes `config.CONTEXT_MAX` mid-turn (500K, scaled likewise) | Once per context: push `[harness] context at the limit: finish the step in hand and post a `recap` in #<attended> now. You are recast when this turn ends.`; recast at the turn boundary per the ladder (§3.4), the system comment naming the cause |
| Character unresumable when it must act | Recast at the turn boundary per the ladder (§3.4) |
| Sub-story's ball reaches author or terminal | The triggering comment is delivered to the author character like any other (cross-story) |
| Human acts as author on a character-owned sub-story | Applied; the resulting system comment is delivered to the owning character |
| Human types in a character's context view | Posted as a human comment in the character's attended thread (root comment addressed to it, if it attends nothing) |
| Story becomes terminal | Every character retires: Cancel stops each live context now; Approve lets a mid-turn context finish its turn (its verbs are already rejected). Nothing is delivered to a retired character; Reopen resumes the protagonist |

**The reading** is the input side of the context's latest API call (§1), pushed like a steering comment
the moment a line is crossed: the character is told mid-turn, not at the next delivery. A recap lowers
nothing; only recast does. Claude Code's own compaction is off in every context the harness spawns
(`DISABLE_AUTO_COMPACT=1`): the ladder is the only compaction, and a `compact_boundary` event is an
error row in the transcript.

`AskUserQuestion` does not exist under `claude -p` (verified 2026-08-31); `yield --question`
with `options` is the only way to ask.

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
with `(phase, ball)`; cast with roles; attachments; then the call-in note (or Start note), then
the phase skill (§5.3). A recast context's brief carries its situation before the skill: "you are
a recast of <name>; your predecessor's recap is above; you were attending #t; n items wait in
your inbox; you await …". A forked friend gets no brief — its context already holds everything,
the phase skill included — only the call note and "you are a fork of <name>: you cannot change
its plan; if the author's point must reach it, `@<name>` it." The contract and the role's
instructions are in the system prompt (§5.3), not the brief.

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

New context = a fresh system prompt (§5.3, which carries the role's instructions) + brief (§3.1,
which includes recaps and ends with the phase skill). The recap
source, best first: **(1)** the character's latest `recap` comment if newer than
`config.RECAP_STALE_TURNS`; **(2)** else resume the outgoing context for one final turn that may
only `recap`; **(3)** else nothing — the brief alone (the old "unresumable" path, now the worst
rung). Recast applies to any character and may change role/model; it takes effect at a turn
boundary (a waiting character is at one already); old context becomes `predecessor`. The new
context's first message is the brief with its situation line (§3.1); then the ordinary delivery
loop continues — nothing bespoke.
A recast clears `context_warned` and `context_maxed`: the crossings belong to the context that is gone.
Its system comment reads `recast <name> as <role> (context; rung 1: fresh recap)` when the max line caused
it and `recast <name> as <role> (rung 1: fresh recap)` when the author did; a manual recast already
pending when the max line hits keeps its role and model.

### 3.5 Asides

One UI intent, `stories.aside(key, comment_id) → context_id`, idempotent: a second press reopens
the comment's existing aside. Precondition: the comment's author is a character. The aside is a
**bare context** (`owner = "human"`) with `about = {story_key, comment_id}`, forked from the
memory that wrote the comment: `comment.context`, and nothing else — after a recast the live
context is a different mind that knows the comment only from the brief, so it is never
substituted. The button is disabled when that context is gone or never ran, and while it is
`working` (a mid-turn session file may hold a dangling tool call; a spike may relax this).

`ContextStore.fork(source, *, owner, about=None)` is shared with `call --fork`: the first spawn
uses `--resume <source session> --fork-session` (verified 2026-08-31 — the fork gets its own
session id from `init`, and the source transcript is untouched); later turns resume the fork's
own id.

An aside has the bare-context permission ceiling (explore/read) regardless of the source's role,
and no `HARNESS_CHARACTER_ID`, so every `zharn story` verb is rejected mechanically. Its system
prompt says what it is: an aside — a private copy of <Name> as of its last turn, discussing its
quoted comment in #t; nobody on the story hears it; anything that should change the story
belongs in the author's reply. Asides are the human's: never recast, never retired, untouched by
Approve and Cancel, and absent from the story record — they are found by scanning contexts for
`about`.

## 4. Comments and threads

```
Comment
  id, story_key, thread_id,
  reply_to: comment_id | null,                    # null ⇔ root; replies nest one level
  author: "human" | <character_id> | "system",
  context: <context_id> | null,                   # the live context that wrote it (characters only)
  kind:   text | question | handoff | recap | system,
  body:   markdown,
  mentions: [character_id],
  structured: { questions?: [{text, options: [str], default?: str}],   # question yields, in the document's order
                answers?: [str],                                       # the reply's picks by question index, "" where none
                check?: {cmd, exit, output},
                transition?: {from: [phase, ball], to: [phase, ball]} },
  attachments: [ {path, is_image} ],
  created_at
```

* A thread whose turn = author renders the matching action bar (main thread: the story's cell
  actions; other threads: Reply · Resolve).
* `question.questions` render as numbered rows, each with its `default` named and a button per option. Picks
  accumulate per thread; Reply is enabled by a pick or composer text and posts one comment — `N. <pick>` per
  picked question, then the text — with the picks as `answers`. The picked button of each row stays marked.
* `is_image` attachments render inline.

## 5. Skills

### 5.1 Layout

```
harness/skills/                       # config.SKILLS_DIR: one Claude Code plugin, --plugin-dir at every spawn
  .claude-plugin/plugin.json          # name "zharn"
  VENDORED.md                         # upstream version; every edit to a vendored file, per file
  skills/
    being-a-character/                # meta: in the system prompt (< 150 words)
    planning-a-story/                 # phase: classify, ask once, outline, proceed
    implementing-a-story/             # phase: TDD, delegate, verify, hand off
    delegating/                       # minion · friend · sub-story
    test-driven-development/ systematic-debugging/ verification-before-completion/
    receiving-code-review/ requesting-code-review/    # vendored from superpowers, MIT, LICENSES/superpowers
```

Claude lists every skill as `zharn:<name>`; a character re-reads its phase skill that way when
unsure. Every spawn gets the plugin — bare contexts and asides too; the phase skills are inert
without a story.

A vendored file differs from upstream only in prefix and vocabulary: `superpowers:` → `zharn:`;
"your human partner" → the thread's author (who may be a character); subagent → minion; "dispatch
a reviewer subagent" → `call` a friend. Every edit is listed in `VENDORED.md`. Not vendored, because
their gates are turn flips and their artifacts are comments, friends, minions and sub-stories:
using-superpowers (`being-a-character`), brainstorming (`planning-a-story`), writing-plans and
executing-plans (the outline handoff and Proceed — the story record survives recast, so no plan
file carries context), subagent-driven-development and dispatching-parallel-agents
(`delegating`), using-git-worktrees (`env open`), finishing-a-development-branch (Approve),
writing-skills (its testing half is §5.4).

### 5.2 Contract

Phase/meta skills use superpowers' skeleton (Iron Law, hard gate, rationalization table,
checklist, flowchart only at decision points; descriptions are triggers, never workflow).

`being-a-character` iron laws: (1) never stop while you owe a thread unless a friend or a
sub-story is out — the harness will yield for you and say so; (2) status is not yours to set;
(3) everything you say to anyone is a comment; (4) the phase skill in your conversation is
mandatory — re-read it with the Skill tool when unsure; (5) when told your context is low,
`recap` before anything else; (6) one question yield carries every question as a record, options where choices exist;
handoffs carry evidence — what changed, how verified, where to look first.
`planning-a-story`: classify (spike / bounded / outline) → bounded: `proceed`; spike: minions
read, then `yield --handoff` with the answer; outline: everything you must ask in one
`yield --question`, then `yield --handoff` the outline (steps, files, tests, what is delegated
and to whom), then wait for Proceed. Gate: no file edits while planning. Its rationalization table
names the rule it overrides: "one question at a time" belongs to another harness — a yield ends
the turn, so batch.
`implementing-a-story`: REQUIRED test-driven-development, verification-before-completion,
delegating; protect your context — minions read, friends build, you hold the plot; a friend
reviews each delegated task; handoff body = what changed / how verified / where to look first (the
checks ride along mechanically, §2.2).
`delegating`: the §6 table of AGENT-MODEL.md, plus: reviews are always friends; independent tasks
go out at once, dependent ones in order; `wait` after casting.
`requesting-code-review`: the reviewer is a friend — `call --role <reviewer>` with the reviewer
prompt as the note; the review comes back as comments on that thread.

### 5.3 Delivery

**System prompt.** Stable for the life of a context and never stored: built at every spawn — first
spawn, resume after a crash, Stop, restart or recycle — from config, the role and the skill files
at that moment (a hook on the context store, like placement). Its parts: identity (name, character
id, story key, title); `being-a-character`; the CLI contract (`$HARNESS_CLI`, the verb table); the
role's instructions and its outline rule. Nothing volatile is in it, so every respawn of a context
sends the same bytes and the cache prefix over the resumed conversation survives. Bare contexts and
asides have their own stored prompts (§3.5).

**Situation line.** Every delivery opens with one, then the comment. Threads are named as a character may
name them: the main thread is `#main` (`--thread main` resolves to it in every verb that takes a thread),
any other by its id, with ` of KEY` when the thread belongs to another story:

```
[situation] phase <phase> · attending #<thread> · you owe <threads> · you await <threads or nothing> · in <repo> at <path>[ · recap due]
[<author>] <kind> in #<thread>: <body>
```

`· recap due` appears while the character's context is past the warn line with no recap since the
crossing (§2.3); the line never carries the reading itself.

**Phase skill.** In messages only, never in the system prompt. Sent whenever the story's phase
differs from `Character.phase_seen`, which is then updated — the comparison is against what the
character was last told, not against the action that moved the phase, because an inbox item can be
popped after the Proceed that preceded it.

| Moment | The character receives |
|---|---|
| Fresh context, recast included | The brief ends with the current phase skill (§3.1). |
| Forked friend | No skill; `phase_seen` copies from the source, whose conversation holds it. |
| Any delivery with `phase ≠ phase_seen` | The new phase's skill appended after the comment. |
| Cast `proceed` | `implementing-a-story` on stdout (§2.2). |
| Respawn in the same phase | Nothing — the resumed conversation holds it. |

Friends get the phase skill like the protagonist: the story's phase binds everyone on it.

### 5.4 Testing

Cheap layer, `tests/fake_claude.py` (it echoes its argv and its `--append-system-prompt` in the
init event): the system prompt carries identity, `being-a-character`, the contract and the role's
instructions, and none of phase, attention, owes, awaits, environment; two spawns of one context
across a Proceed get identical prompts; every delivery starts with the situation line; the first
message of a fresh context ends with the phase skill and a fork's does not; Proceed, Back to
planning, Reopen and an inbox pop across a Proceed each append the new skill once, a same-phase
delivery does not; cast `proceed` prints it and the next delivery does not repeat it; a friend
cast in implementing gets `implementing-a-story`.

Paid layer, `tests/skills/<scenario>/` = `prompt.md` + fixture repo builder + `expected.json`
(verbs that must and must not occur). The runner spawns a character with and without the skill
under real `claude -p`, only under `HARNESS_PAID_TESTS=1`, on the CLI's default model unless
`HARNESS_PAID_MODEL` names one (it overrides every role, friends included, for that run); assertions
read `verbs_log`, not transcripts; the last run's baseline and skilled logs are committed beside the
scenario as evidence, each recording the model that ran. Scenarios: outline-before-proceed (an `outline_first` role: one question yield, one
outline handoff, no edits), handoff-not-silence (implementing: a committed handoff with evidence, not a
harness yield), batch-questions (planning with three unknowns: one yield whose document carries options).
New/edited skills: baseline failure first.

## 6. UI

* **Board** (`qml/content/StoryBoard.qml`): columns Backlog · Todo · Planning · Implementing ·
  Done; Canceled behind a filter. Card: key, title, priority, needs-you badge with flavor
  (§2.4, includes waiting side threads; sorted first, counted in header) / waiting-on-character
  muted / live activity, cast avatars with attention state, open sub-story count.
* **Story tab** (`qml/content/Story.qml`): header (key, title, editable description while
  unstarted, role picker + Start with note | phase chip + main action bar); threads with
  replies, option buttons, handoff evidence, resolved threads folded to root + yields + closing
  note; an aside button on any character comment (opens or reopens its aside; disabled while
  the source is working); a composer per thread and
  one for new threads, `@` autocomplete over the cast, `/call <role> [note]` and
  `/fork @Name [note]`; side panel: cast (status: working on #n / waiting / idle / retired ·
  forked from · inbox depth · the context's vitals · Recast button → role/model dialog), sub-stories
  (phase+ball → open).
* **Context vitals** (`qml/ui/Meter.qml`, on every cast row and the Contexts pane header): the
  reading (§1) laid on the harness's runway — the bar ends at `CONTEXT_MAX`, a tick marks
  `CONTEXT_WARN`, both scaled to the window (`contexts.context_lines`); the window itself is not the
  frame. Beside it the reading in tokens (`312K`), then `recap due` while a recap is outstanding
  (§2.3) — the only state that colors the bar and the text amber — then `recast at turn end` once
  past the max line, then turns and cost. The tooltip carries the exact count, the window and both
  lines. A context with no reading yet shows an empty bar. Contexts tree rows carry the reading
  before turns and cost; a predecessor row reads `recast at <reading>`.
* **Contexts** (`qml/content/Contexts.qml` + `ContextView.qml`): list of all contexts —
  characters' with recast lineage, bare and asides (titled "aside on #t · <Name>", under their
  story), minions under dispatcher — and **New Context**. Views
  per §3.3. Bare contexts carry **Promote to story**: dialog (title, description) → story in
  `planning` with this context cast as protagonist; brief injected on promote.
* **Notifications**: needs-you transitions on human-authored stories and threads raise
  `notify.py`.

## 7. Tests

* `tests/test_lifecycle.py`: every cell × every action of §2 as a table, per-thread turn flips,
  rejections, §2.4 invariants. Resolve: rejections (main thread, turn = cast, non-author,
  terminal story), reopen-on-comment and reopen-on-yield, the Approve/Cancel terminal sweep,
  the Approve comment's merged lines and `structured.merged`, needs-you dropping resolved
  threads.
* `tests/test_cli.py`, `test_ipc.py`, `test_stories.py`: each verb, lead/author checks, `wait`
  as a guard, delivery by status (attended push vs inbox, one pop per turn, attention moves),
  the quiet check at turn end (normal end, crash, Stop), retirement on Approve/Cancel, Approve
  fast-forwards its environments (workspace spec §4.8), `call --fork` and `/fork`, recap in the
  attended thread, recast ladder rungs 1–3 with the situation line, cross-story sub-story
  delivery.
* Asides: intent idempotency, the fork-source rule (`comment.context` or disabled: gone, never
  ran, or working), the read ceiling, verb rejection without `HARNESS_CHARACTER_ID`,
  survival across recast and Approve/Cancel, absence from the story record.
* `tests/test_ui_story.py`, `test_ui_board.py`, `test_ui_contexts.py` via `tests/ui.py`: action
  bars per cell and per waiting thread, option buttons, needs-you sort/count, `@` and `/call`,
  context-view input posting comments, New Context, Promote.
* `tests/test_ui_cast.py`: the vitals line and meter frame from a reading, amber with `recap due`
  past the warn line and back once a recap lands (cast row and Contexts pane alike), a
  predecessor row naming the reading it was recast at.
* `tests/test_stories.py`, `test_agents.py`: §5.4 cheap layer — the stable system prompt, the situation
  line, the phase skill on `phase_seen` changes.
* `tests/skills/`: §5.4 paid layer.
* Context usage: the reading and window from hand-built events and through replay
  (`test_stream_interpreter.py`, `test_contexts_unit.py`); a fork's inherited reading; `DISABLE_AUTO_COMPACT`
  at every spawn; warn once with `recap due` until a recap, max marking a recast that fires at the boundary
  and names its cause, small-window scaling, nothing on an idle or retired character (`test_stories.py`).

## 8. Out of scope

Pull requests; workspaces, repos and environments themselves
([their own spec](workspace-model.md)); roles beyond `outline_first` and `instructions`; multi-machine
execution; harness-spawned minions (`minion`, `minion --fork` — Claude's native `Agent` tool
serves for now); a mechanical cap on guest mention loops; escalating an aside into a thread (a
thread led by a forked friend is the manual path).
