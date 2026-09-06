# The skill you wake up with is your position's, not just the story's

*Proposal, 2026-09-05. Depends on ZHAR-5 (model/effort/preset), which makes `position` a stored
field; it lands on top of that. Expires when it lands; the standing text goes into
`docs/specs/story-lifecycle.md` (§1, §5.1, §5.2, §5.3, §5.4) and a new
`harness/skills/skills/being-a-friend/SKILL.md`.*

A friend is handed the protagonist's playbook. `harness/skills.py` keys the injected skill on the
story's phase alone — `PHASE_SKILLS = {"planning": …, "implementing": …}` — and
`StoryStore._phase_skill_due` looks up nothing else. The lifecycle spec states it as a rule
(§5.3): *"Friends get the phase skill like the protagonist: the story's phase binds everyone on
it."* That sentence is the bug, written down.

What it costs is not noise. In ZHAR-5, context `ctx_w2h8nruiu7`, the friend **Scribe** was called
onto a side thread to write four markdown files, with a note ending "Do not commit; hand off with
what you changed and the test count. … do not yield a question." Appended to that same message,
`implementing-a-story` told it:

* "You hold the plot; everyone else holds a piece" — Scribe holds one piece.
* "Split the outline into tasks a friend could take" and "a reviewer friend reads each delegated
  task" — neither is Scribe's job.
* "`yield --handoff` **on the main thread**" — structurally impossible. Only a thread's lead
  yields in it, and main's lead is the protagonist (§2.4).
* "commit in your environment … rebase onto its target … the handoff names the commit" — the
  tree, target and checks gates are preconditions of a *main-thread* handoff in `implementing`
  ([workspace spec](../../specs/workspace-model.md) §4.6: "Side threads are not gated").

So one message carried a task and its own contradiction. A character reading it must decide which
half of its input to disbelieve, and nothing in the harness tells it which.

The fix is one axis. A character's **position** — what it is by where it was cast — already
decides its instructions, its outline rule and its permission ceiling. It should decide its skill
too.

## Positions taken

| # | Question | Position |
|---|---|---|
| 1 | Does a friend get a friend skill *instead of* or *as well as* the phase skill? | Instead. Appending a corrective leaves the four contradictions in the message; a character cannot be asked to arbitrate between two mandatory skills. |
| 2 | One friend skill, or one per phase? | One. A friend's job barely moves across planning and implementing, and the situation line already names the phase. The planning gate — read, do not edit — is a line inside the one skill. |
| 3 | Does the bare position get a skill? | No. A bare context is not on a story; the phase skills are already inert there (§5.1). |
| 4 | What does the harness track to know a skill is due? | The skill's **name**, not the phase. `Character.phase_seen` becomes `Character.skill_seen`. Every case below falls out of that substitution with no special-casing. |
| 5 | Does a forked friend get the skill? | Yes — a change from today. A protagonist forked into a friend carries `implementing-a-story` in its conversation and now holds one piece; a short corrective is exactly what it needs. |
| 6 | Can a preset switch the friend skill off? | No. It joins `being-a-character` and the phase skills in the always-on set. That set should also be force-included in every *built* tree, reversing a call ZHAR-5 made (§4) — the one adjacent fix here, and separable from the rest. |
| 7 | Does `implementing-a-story` shrink? | No. It is the protagonist's, and it is correct for the protagonist. It gains one line naming what its friends were told. |

## 1. The axis: position × phase

`harness/skills.py` gains a second table and one function; `phase_skill` goes away.

```python
PHASE_SKILLS    = {"planning": "planning-a-story", "implementing": "implementing-a-story"}
POSITION_SKILLS = {"friend": "being-a-friend"}   # a position leading no story takes one skill in every phase

def skill_name(position: str, phase: str) -> str: ...
def skill_for(position: str, phase: str) -> str: ...   # the body, or ""
```

A position in `POSITION_SKILLS` takes its skill in every phase; anything else falls through to
the phase table. `bare` is in neither and takes none. Terminal phases stay the caller's business,
as they are today.

## 2. Delivery: `skill_seen`

`Character.phase_seen` (the phase whose skill it last received) becomes `Character.skill_seen`
(the *name* of the skill it last received). `StoryStore._phase_skill_due` becomes `_skill_due`
and compares names. Nothing else about delivery moves: the skill still rides a message, never the
system prompt; it is still appended after the comment; the caller still saves.

Every case follows from the substitution alone:

| Moment | Today | After |
|---|---|---|
| Protagonist, any phase | correct | unchanged — the name moves 1:1 with the phase |
| Friend cast fresh | its brief ends with the lead's playbook | its brief ends with `being-a-friend` |
| Friend across a Proceed | `implementing-a-story` arrives mid-thread — the ZHAR-5 defect | the due name is unchanged, so nothing is sent |
| Forked friend | `phase_seen` is copied from the source and no skill is sent | the copy is dropped; due ≠ seen, so `being-a-friend` rides the fork note |
| Recast friend | `phase_seen := None`, then the phase skill | `skill_seen := None`, then `being-a-friend` |
| `cast proceed` | sets `phase_seen := "implementing"` | sets `skill_seen := "implementing-a-story"`; `proceed` is main's lead only, so the effect is unchanged |
| Respawn in place | nothing | nothing |

The fork case is the only behaviour change beyond the friend's skill itself, and it is the one
the old rule got backwards: a fork's conversation holds the *source's* skill, which is the wrong
one precisely when the fork changed position.

## 3. `being-a-friend`

A new skill in the tree, in the house shape (an iron law, the gates, a rationalization table, a
checklist). Its description is a trigger, not a workflow, and begins "Use when" as every skill's
must. It runs about 500 words against `implementing-a-story`'s 774 — shorter, but not as short as
"a friend does one piece" suggests, because each law below is one a friend gets wrong by default
and none of them compresses to a clause. It sits between `delegating` (369) and
`planning-a-story` (670).

Each law it carries is a rule the harness already enforces somewhere, restated where the friend
will read it:

| It says | Because |
|---|---|
| Your handoff goes in the thread you lead, never `#main` | §2.4: only a thread's lead yields in it |
| Your author is whoever called you — usually a character, not the human | §2.2 `call`: the caller authors the thread |
| Your thread is not gated: no tree check, no ancestry check, no `checks` | workspace §4.6: side threads are not gated |
| You share the lead's tree; commit only when your note says to, and never rebase it | workspace §4: friends share a tree, stories get a branch; the lead's main handoff is where the work is declared done |
| Story in planning? Read, run what changes nothing, report — edit nothing | §5.2's planning gate binds everyone on the story |
| `proceed` and `approve` are not yours | §2.2 preconditions |
| Do the note's task and only it; decide what it leaves open and name the decision in the handoff | a question costs your caller a turn |
| Never end a turn in silence | §2.3's quiet check, which will yield your last words under your name |

It keeps `zharn:test-driven-development` and `zharn:verification-before-completion` as required
sub-skills, and names `zharn:delegating` as available but rarely yours.

Its rationalization table answers the four contradictions above by name — "the lead's skill said
commit before handing off", "I'll hand off on `#main` so the author sees it", "the outline needs
splitting into tasks", "I should call a reviewer for my own work" — so that a friend that has
*also* read the protagonist's skill, from a fork or from the tree, knows which half is its own.

## 4. The always-on set lives in the tree, not only in the prompt

*This section is separable. It fixes something next to the friend skill rather than part of it;
cut it and §§1–3 still stand.*

A preset names the subset of the tree a character can invoke, and the harness injects
`being-a-character` and the phase skill regardless. §5.1 already sees where that leads and accepts
it: "a preset that leaves them out of the plugin only means the character cannot re-read them with
the Skill tool." `DEFAULT_PRESETS`' `builder` and `reviewer` leave them out, `preset_skills` returns
the list as written, and `plugin_dir` copies exactly that — so the acceptance is real, not an
oversight.

The acceptance is still wrong, because law 4 of `being-a-character` is not advice. It tells the
character the injected skill is mandatory and to re-read it with the Skill tool when unsure — and
under `builder` there is nothing to re-read. A law a character cannot obey teaches it that the
laws are approximate, which is the one thing the meta skill cannot afford.

So `skills.plugin_dir` unions the always-on set into `names` before it stamps and builds. The
preset still decides everything else; `["*"]` is unaffected; `preset_skills` keeps returning what
the preset actually names. The alternative — drop "re-read it with the Skill tool" from law 4 —
is cheaper and was considered: it is rejected because a long context re-reading its mandatory
skill is exactly the recovery the law exists to offer.

`being-a-friend` is why this lands here rather than later: it is the fourth member of that set,
and the one a friend has most reason to re-read.

## 5. What else moves

* `being-a-character` law 4 names both phase skills by hand ("re-read `zharn:planning-a-story` or
  `zharn:implementing-a-story`"). It becomes position-agnostic — the skill your messages carried
  is the mandatory one, re-read it with the Skill tool — which is also shorter, so the skill stays
  under its 150-word ceiling.
* `implementing-a-story` gains one line: the friends you call are told `being-a-friend`, which is
  why their handoffs land in their own threads and their trees are not gated.
* `docs/specs/story-lifecycle.md`: §1 (the record field), §5.1 (the tree listing, and the
  paragraph that accepts a preset leaving the injected skills unlistable), §5.2 (the contract
  paragraph), §5.3 (the delivery table, and the sentence that states the defect), §5.4 (the
  assertion list).

## 6. Testing

Cheap layer, on `tests/fake_claude.py` as §5.4 already does:

* `skill_name` over the position × phase matrix, terminal phases and the bare position included.
* A friend cast in `implementing` receives `being-a-friend` and none of `implementing-a-story`.
* A friend across a Proceed receives nothing new; a protagonist across the same Proceed receives
  `implementing-a-story` exactly once. Both from one story, in one test.
* A friend forked from the protagonist receives `being-a-friend` after the fork note.
* A recast friend's brief ends with `being-a-friend`.
* Tree hygiene: `being-a-friend` joins the sets `tests/test_skills.py` asserts over — the
  "Use when" description, the forbidden-vocabulary list, and the word bans that already cover the
  other injected skills.
* Every preset's built tree contains the always-on set (§4).

Paid layer, a new scenario `tests/skills/friend-stays-in-lane/`: a friend called in
`implementing` with a note that forbids committing. Expected — `yield --handoff` on its own
thread; must not occur — `yield` on main, `call`, `proceed`, a commit. §5.4 requires a baseline
failure before a new skill is accepted, and Scribe's transcript is that baseline: it is the
unskilled run, already recorded.

## 7. Not doing

* **A per-phase friend skill.** Two files to keep true for a job that does not change across the
  two phases.
* **Making `implementing-a-story` position-neutral.** It would lose the thing it is for. The
  protagonist's playbook should read as the protagonist's.
* **A skill for the bare position.** A bare context has no story, no thread and no author.
* **Letting a position override its skill from config.** `CAST_POSITIONS` carries what a role
  carried; the skill a position wakes up with is the harness's, like the phase skills.
