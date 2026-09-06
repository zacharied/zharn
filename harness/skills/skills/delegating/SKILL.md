---
name: delegating
description: Use when a piece of work should be done by someone other than you — reading that would fill your context, a parallel build, a review, or work that needs its own description and validation
---

# Delegating

Three tools, one question each.

| Use a… | when… | how |
|---|---|---|
| **minion** | you need a result and nobody needs to see the process | the native Agent tool; its output is your contract with it |
| **friend** | others should see the contribution as a participant: a review, a second opinion, a parallel build | `$HARNESS_CLI story call --as Name [--model M] [--effort E] [--preset P] [--fork] --note "…"`, then `wait` |
| **sub-story** | the work should be described and validated on its own | `$HARNESS_CLI story create --title … --description … --start [--model M] [--effort E] [--preset P]`; you are its author |

## Rules

- Reviews are always friends. A review nobody can see is not a review.
- Independent tasks go out at once, one friend each. Dependent tasks go out in order, each after the previous handoff.
- Every call note is complete on its own: the task, the files, the tests that prove it, the branch to build on. The friend has the story record but not your head.
- `--fork` when the friend needs your reasoning so far (a second opinion); fresh when it needs a clean view (a review, a build).
- The three picks are optional and default to the position's: name `--model` and `--effort` when the piece wants a different mind, `--preset` when it should wake with a smaller set of skills (`$HARNESS_CLI cast options` lists all three).
- `wait` after casting, then end your turn. Do not poll; the handoffs wake you.
- Nest sub-stories one level. Deeper is almost always a sign the outline was wrong.

## The independence test

Two tasks are independent when neither reads a file the other writes and neither's tests depend on the other's code. Anything else is dependent: sequence it.

## Rationalizations

| Excuse | Reality |
|---|---|
| "It's faster to do it myself" | Faster now, and your context pays for it for the rest of the story. |
| "I'll send a minion to review" | Minions are invisible. The author cannot read their verdict; a friend's review is on the record. |
| "I'll call one friend for everything" | One friend serializes what could run in parallel and holds every file in one context. Split it. |
| "I'll keep working on the same files while the friend builds" | Two writers, one tree. Give the friend the files; take other ones, or wait. |
