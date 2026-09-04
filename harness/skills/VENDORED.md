# Vendored skills

Source: superpowers 6.3.0 (https://github.com/obra/superpowers), MIT, Jesse Vincent — `LICENSES/superpowers`.
The next sync is a diff against 6.3.0. Every file below differs from upstream only by the edits listed.

Rules (lifecycle spec §5.1), applied with `sed`: `superpowers:` → `zharn:`; "your human partner's" →
"the author's"; "your human partner" → "the thread's author" (an author may be a character); a bare
"your partner" → "the thread's author"; a subagent reviewer → a friend cast by `call`; references to
skills that are not vendored are dropped.

| File | Edits |
|---|---|
| test-driven-development/SKILL.md | human-partner rule (3 hits) |
| test-driven-development/writing-good-tests.md | human-partner rule (2 hits); the `(superpowers:writing-skills)` reference dropped |
| systematic-debugging/SKILL.md | prefix rule (2 hits); human-partner rule (2 hits); heading "your human partner's Signals You're Doing It Wrong" → "The author's signals you're doing it wrong" |
| systematic-debugging/condition-based-waiting.md, condition-based-waiting-example.ts, defense-in-depth.md, root-cause-tracing.md, find-polluter.sh | verbatim. Not copied: CREATION-LOG.md, test-academic.md, test-pressure-*.md (the author's own test artifacts) |
| verification-before-completion/SKILL.md | verbatim |
| receiving-code-review/SKILL.md | human-partner rule (9 hits); one bare "your partner" → "the thread's author" |
| requesting-code-review/SKILL.md | rewritten: the reviewer is a friend cast by `call`, the template is the call note, the review is its handoff; a "minion can review" rationalization added |
| requesting-code-review/code-reviewer.md | header and fence adapted to a call note; "You Do Not Dispatch Subagents" → "You Do Not Call Friends or Send Minions"; a "How to Report" section (the review is a `yield --handoff`) |
