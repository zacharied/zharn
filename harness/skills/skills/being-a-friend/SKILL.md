---
name: being-a-friend
description: Use when you were called onto a thread for one piece of a story — before you build, commit, or end a turn
---

# Being a friend

You were called onto one thread for one piece of this story. The note that called you is your brief; whoever called you reads your handoff, not your diff.

## The Iron Law

```
YOUR TURN ENDS IN YOUR OWN THREAD — A HANDOFF, A QUESTION, OR A WAIT
```

Stop with nothing yielded and nothing awaited, and the harness posts your last words as a handoff under your name. `#main` is not yours: only a thread's lead yields in it, and that is the protagonist.

## Where you stand

| | |
|---|---|
| Your author | whoever called you — usually a character, not the human. Your yields reach them. |
| Your thread | the one you lead. Comment elsewhere only when your note sends you. |
| Your tree | the lead's, shared. Commit only when your note says to; never rebase. |
| Your gate | none. No tree check, no ancestry check, no repo checks — those are the lead's, on `#main`. |
| Not yours | `proceed`, `approve`, the outline, calling reviewers. |

Planning phase — the situation line names it — you read, run what changes nothing, and report; edits wait for `implementing`. Otherwise `env open`, stay in the files your note named, build test-first (`zharn:test-driven-development`), prove it (`zharn:verification-before-completion`), and send a minion for anything large to read (`zharn:delegating`). What the note leaves open, you decide — and name the decision in your handoff.

## The handoff

`yield --handoff` in your thread, body in this order: **what changed** (files and behaviour, one line each), **how verified** (the commands you ran and what they printed — counts, not adjectives), **where to look first** (the one file or test that shows it working).

## Rationalizations

| Excuse | Reality |
|---|---|
| "The other skill said to commit before handing off" | That one is the lead's. Your thread is not gated and the tree is shared; the lead declares the work done. |
| "I'll hand off on `#main` so the author sees it" | Only its lead yields there. Your handoff in your own thread wakes whoever called you — that is how it reaches `#main`. |
| "The outline needs splitting into tasks" | It was split already. Your task is the note. |
| "I'm nearly done, I'll fix the next thing too" | Two writers, one tree. What you touch outside your note collides with someone. |
| "I'll ask a quick question" | Decide it and record it, unless the answer changes what you were asked to build. |
| "I finished; my last message says so" | Prose outside the CLI reaches nobody. `yield --handoff`. |

## Checklist

- [ ] The note's task, and only it
- [ ] Test-first; verified by commands you ran and quoted
- [ ] Open decisions made, and named in the handoff
- [ ] Tree left as the note asks
- [ ] `yield --handoff` in your own thread
