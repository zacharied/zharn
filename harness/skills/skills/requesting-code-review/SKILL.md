---
name: requesting-code-review
description: Use when completing tasks, when a friend's build lands, after a major feature, or before your handoff on the main thread — to verify work meets requirements
---

# Requesting Code Review

Call a reviewer friend to catch issues before they cascade. The reviewer gets precisely crafted context for evaluation — never your session's history.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:**
- After each task a friend built for you
- After completing a major feature
- Before your handoff on the main thread

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing a complex bug

## How to Request

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or the branch this environment was cut from
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Call a reviewer friend:**

Fill the template at [code-reviewer.md](code-reviewer.md) and pass it as the call note, then wait:

```bash
$HARNESS_CLI story call --role <a reviewing role> --as Reviewer --note "<the filled template>"
$HARNESS_CLI story wait     # then end your turn; the review wakes you
```

**Placeholders:**
- `[DESCRIPTION]` - Brief summary of what you built
- `[PLAN_OR_REQUIREMENTS]` - What it should do (the outline, the task text)
- `[BASE_SHA]` - Starting commit
- `[HEAD_SHA]` - Ending commit

**3. Act on feedback** — the review arrives as the reviewer's handoff in its thread:
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back in that thread if the reviewer is wrong (with reasoning)

## Example

```
[Implementor's handoff for Task 2 just landed: verification function added]

You: Review before Task 3.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

$HARNESS_CLI story call --role claude-deep --as Reviewer --note "…filled template…"
$HARNESS_CLI story wait
[turn ends]

[Reviewer's handoff wakes you]:
  Strengths: Clean architecture, real tests
  Issues:
    Important: Missing progress indicators
    Minor: Magic number (100) for reporting interval
  Assessment: Ready to proceed

You: [reply in Implementor's thread: add progress indicators]
[Continue to Task 3]
```

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "I'll just review the diff myself instead of calling a reviewer" | You hold the plot — reviewing the diff inline burns the context you need to keep driving the work. Call a reviewer: the diff and the evaluation live in its context, and only the findings come back as comments. |
| "The reviewer needs my whole session history to understand the change" | Hand it precisely crafted context, never your session's history. That keeps the reviewer on the work product, not your thought process. |
| "A minion can review it" | Minions are invisible. A review nobody on the story can read is not a review. Reviews are friends. |

## Red Flags

**Never:**
- Skip review because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: [code-reviewer.md](code-reviewer.md)
