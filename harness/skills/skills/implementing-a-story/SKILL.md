---
name: implementing-a-story
description: Use when the story you are cast on is in the implementing phase — from the moment Proceed lands until your handoff is accepted
---

# Implementing a story

Build what planning settled, prove it, hand it off with evidence. You hold the plot; everyone else holds a piece.

**REQUIRED SUB-SKILLS:** `zharn:test-driven-development` for every change; `zharn:verification-before-completion` before every claim; `zharn:delegating` for every piece you do not build yourself.

## The Iron Law

```
THE TURN ENDS WITH A HANDOFF, A QUESTION, OR A WAIT — NEVER WITH SILENCE
```

Stop with nothing yielded and nothing awaited, and the harness posts your last words as a handoff under your name. That is the worst handoff you will ever write.

## Protect your context

Minions read, friends build, you hold the plot. A file you read stays in your context for the life of it; a minion's report is a paragraph. A friend's build lives in its own context; only its handoff reaches yours. About to read a fourth large file, or write a second module yourself? Delegate instead.

## Shape of the work

1. `$HARNESS_CLI env open <repo>` and `cd` there before touching anything. Checks run at your handoff in that environment.
2. Split the outline into tasks a friend could take without your history. Independent tasks go out at once; dependent ones in order (`zharn:delegating`).
3. Each task you build: `zharn:test-driven-development`. Each task a friend built: reply in its thread with what to fix, or `resolve` it.
4. After each delegated task lands, a reviewer friend (`call --role reviewer`) reads it (`zharn:requesting-code-review`). Reviews are always friends — never you, never a minion.
5. `wait` after casting; end your turn; the handoffs wake you.
6. Before the handoff: `zharn:verification-before-completion`. Run the repo's checks yourself first; a refused handoff is a wasted turn.

## The handoff

`yield --handoff` on the main thread. The body IS this, in order:

```
What changed: <files and behaviour, one line each>
How verified: <the commands you ran and what they printed — counts, not adjectives>
Where to look first: <the one file or test that shows the change working>
```

Checks attach mechanically. Open sub-stories block the handoff: finish or cancel them first.

## Rationalizations

| Excuse | Reality |
|---|---|
| "I'll report progress in my final message and stop" | Nobody reads your final message. The harness yields it for you and says you went quiet. `yield --handoff` it yourself. |
| "It's a small change, I'll skip the test" | Small changes break. `zharn:test-driven-development` has no size threshold. |
| "I'll review my friend's work myself, it's faster" | Reviewing burns the context you hold the plot with. Call a reviewer. |
| "Tests probably pass" | Run them. `zharn:verification-before-completion`: evidence before claims. |
| "I'll ask the author a quick question mid-build" | A question yields the main thread and stops the build. Decide and note the decision in the handoff, or batch it with everything else you need. |
| "I'll hand off now and finish the rest after" | A handoff says the work is done. Half-done work is a `comment`; then keep going. |

## Red flags

- Ending a turn with `you owe` non-empty and `you await nothing` in your situation line
- A handoff body without a command and its output
- Reading a file a minion could have summarized
- Editing the main checkout instead of your environment

## Checklist

- [ ] In your environment (`env open`)
- [ ] Tasks split; delegated ones out; `wait`
- [ ] Every change test-first; every delegated task reviewed by a friend
- [ ] Checks run and green (or `--despite-checks`, and say why in the handoff body)
- [ ] Handoff: what changed / how verified / where to look first
