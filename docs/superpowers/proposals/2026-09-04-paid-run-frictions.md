# What the paid run taught: question documents, a true guard, `#main`, and the tree at handoff

*Proposal, 2026-09-04. Expires when it lands; the standing text goes into
`docs/specs/story-lifecycle.md` (§2.2, §4, §5) and `docs/specs/workspace-model.md` (§4.6).*

The first paid run of the skills layer (Sonnet 5, three scenarios, eight character turns, commit
60e21d3) passed, and its transcripts showed four places where the harness and the model disagree
about what is natural. None was a skill failure. Each is a shape the harness offers that the model
reaches for wrongly, or does not offer at all.

## Positions taken without a ruling

Each was put to the author and not contested, or follows from what was.

| # | Question | Position |
|---|---|---|
| 1 | Is a single question with no options still a document? | Yes. One shape per kind: two accepted forms give the model a choice to get wrong. |
| 2 | Does clicking an option still post the reply? | No. Picks accumulate, one row per question; Reply posts them all with the composer text. A click posting immediately only ever worked for one question. |
| 3 | Is `default` validated against `options`? | No. It is a string the character says for each question; the row shows it. Rejecting a default that names no option would cost a round trip for nothing. |
| 4 | Is there a `--despite-tree` flag? | No. Approve merges the branch; what is not committed is not in the story. Checks measure quality and get a knob; the tree gate protects the work and gets none. |
| 5 | Do untracked files count as dirty? | Yes. A new test file is untracked and is the work. The character commits or ignores it. |
| 6 | Where is a malformed document refused? | Invalid JSON: in the CLI, like the "exactly one of --question / --handoff" exit, and not in `verbs_log`. Valid JSON with the wrong shape: in the store, as a rejection, logged like any other. |
| 7 | Does the CLI `reply --body` learn `answers`? | No. A character answering another character's question writes prose. Only the story view composes `answers`. |

## 1. Question yields carry a document

**What the run showed.** Every batched yield in the run carried several numbered questions in one
prose body, and `--options` is one flat list rendered as one button row. In both skilled planning
runs Sonnet improvised `|` separators inside the list ("yaml|repo root"), which the harness stored
verbatim and would have rendered as buttons whose click answers nothing. The comma is a separator
with no escape, so an option that contains one splits in two.

**The change.** A question yield reads a JSON document from stdin. `--body` belongs to handoffs.

```
$HARNESS_CLI story yield --question [--thread t] <<'EOF'
{
  "body": "Three decisions before I plan.",
  "questions": [
    {"text": "File format?", "options": ["toml", "json", "yaml"], "default": "toml"},
    {"text": "Where does the file live?", "options": ["the repo root", "the user's config dir"]},
    {"text": "Anything else the config should carry?"}
  ]
}
EOF
```

`body` is an optional preamble. `questions` is a non-empty list; each has `text` (non-empty),
optional `options` (strings; absent or empty means free text) and optional `default` (a string).
The harness numbers them. A quoted heredoc turns off every shell-escaping problem at once, and
the cost of JSON, no literal newlines in strings, disappears once each question is one record and
the body is a line.

**Stored.** `structured.questions = [{text, options, default?}]`, options always a list. The reply
that answers it carries `structured.answers = [str]`, aligned by index, `""` where a question
was not picked.

**Rendered to a character** (brief and delivery header), one line per question:

```
[you] question in #main: Three decisions before I plan.
  1. File format? (toml, json, yaml; default toml)
  2. Where does the file live? (the repo root, the user's config dir)
  3. Anything else the config should carry?
```

**Rendered to the human.** The story view shows the preamble, then each question numbered with
its own button row when it has options and its default named. Picks accumulate in the thread; the
composer holds free text; Reply is enabled when either exists and posts one comment whose body is
`N. <pick>` per picked question followed by the composer text, with the picks in `answers`. The
picked button of each row stays marked afterwards.

**Everything downstream moves with it.** The `Yield` action carries `questions`, the IPC verb
and `verbs_log` record them, `render_brief` and delivery print the numbered lines, the system
prompt's verb table shows the heredoc, the fake claude's `yield-question` script writes a
document, and the paid runner's `question_has_options` reads `questions`.

## 2. `wait` rejects only the case that would go quiet

**What the run showed.** In five of eight turns the character yielded and then called `wait`
with no text in between, and was refused: "you await nothing and owe nothing either, just end
your turn". The intent was right. The character was done and something would wake it.

**The change.** The spec already calls `wait` a guard, not a block. A guard fails only when
stopping would be wrong, and stopping is wrong in exactly one state: the character owes a thread
and awaits nothing, so its turn would end in silence and the harness would yield for it. `wait`
keeps rejecting that case ("you await nothing and owe #t: yield instead"). When the character
awaits nothing and owes nothing it now succeeds: "you await nothing and owe nothing: end your
turn; a reply will wake you". No skill text changes; the skills already say a yield ends the turn.

## 3. The main thread is `#main` everywhere the harness speaks

**What the run showed.** The brief names the main thread `#main`; the situation line and the
delivery header print its `thr_` id; the CLI resolves only the id. A character wrote
`--thread main` on its first yield, was refused, and retried without the flag.

**The change.** One label function: the main thread is `main`, any other thread is its id.
The brief, the situation line (`attending`, `you owe`), the awaits line, and the delivery header
(`in #main`, `in #main of SUB-1` across stories) all use it, and `--thread main` resolves to the
main thread of whichever story the verb acts on, in every verb that takes a thread. This is the
name the harness already uses, not an alias for an old one.

## 4. The tree is clean at an implementing handoff

**What the run showed.** In handoff-not-silence the baseline committed its work and the skilled
run handed off with two modified files and no commit. The workspace spec says a story's results
reach the parent branch through Approve, which merges the story's branch. Uncommitted work at
handoff is work the merge drops.

**The change.** At a handoff on the main thread of an `implementing` story, before the checks
run, the CLI runs `git status --porcelain` in every environment of the story. Any output refuses
the handoff and prints it per repo: "handoff refused: uncommitted changes in fixture
(<path>): M hello.py, ?? __pycache__/. Commit them and retry." There is no flag past it. Side
threads are not gated: friends share the protagonist's tree, and the protagonist's handoff is
where the story's work is declared done.

The implementing skill says it in three places: the shape of the work ("commit before the
handoff; the handoff names the commit"), the rationalization table ("I'll leave committing to the
author" against "Approve merges the branch; what isn't committed isn't in the story"), and the
checklist. The `env.checks` plan lists every environment, not only those with `checks`, so one
request serves both gates.

## 5. Evidence

The paid scenarios re-run after the change, on Sonnet 5 again so the runs compare:
batch-questions proves the document shape is written cleanly first try, and handoff-not-silence
gains `"committed": true`, which the runner asserts as every environment clean with at least one
commit past its base. The evidence files beside each scenario are replaced.

## Out of scope

* `answers` from the CLI `reply` verb (position 7).
* Committing on the character's behalf. The handoff and the commit stay two acts.
* Logging CLI-side refusals (the flag error, invalid JSON, the checks gate, the tree gate) in
  `verbs_log`. None of them is today, and the paid assertions do not need them.
