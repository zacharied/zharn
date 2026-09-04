---
name: planning-a-story
description: Use when the story you are cast on is in the planning phase — before treating the brief as work to do, before touching any file
---

# Planning a story

You are deciding what this story is and what the author must settle before anyone builds. The story record survives every recast, so the outline you hand off *is* the plan; there is no plan file.

## The Iron Law

```
NO FILE EDITS WHILE PLANNING
```

Read anything. Run anything that changes nothing. Send minions to read. Write nothing to the tree until Proceed lands.

## Classify first

```dot
digraph classify {
    "What does the brief ask?" [shape=diamond];
    "Spike: an answer, not code to keep" [shape=box];
    "Bounded: a change to a flow that already exists here" [shape=box];
    "Outline: a new subsystem, restructuring, or interfaces others depend on" [shape=box];
    "What does the brief ask?" -> "Spike: an answer, not code to keep" [label="can we / is it possible"];
    "What does the brief ask?" -> "Bounded: a change to a flow that already exists here" [label="the flow is here to read"];
    "What does the brief ask?" -> "Outline: a new subsystem, restructuring, or interfaces others depend on" [label="anything else, or in doubt"];
}
```

In doubt between two, take the heavier one. The ratchet is one way: complexity found later upgrades the class; nothing downgrades.

| Class | What you do |
|---|---|
| Spike | Minions read and try; you `yield --handoff` the answer with what was tried. Anything built is labeled throwaway. |
| Bounded | `proceed --note "<what changes, how it is tested>"` — unless your role requires an outline (your system prompt says so); then a short outline handoff. |
| Outline | Ask everything you must in one `yield --question`; when answered, `yield --handoff` the outline; end your turn and wait for Proceed. |

## The outline

A handoff whose body has, in this order: the steps; the files each step touches; the tests that prove each step; what is delegated and to whom (minion, friend, sub-story — `zharn:delegating`). Under 400 words. Nothing in it is a question: the questions went out in the yield before it.

## Asking

One `yield --question` carries every unknown. Number them; give `--options` for the ones with natural choices; say your default for each. The author answers once.

## Rationalizations

| Excuse | Reality |
|---|---|
| "I'll ask one question at a time, it's more conversational" | That rule belongs to another harness. A yield ends your turn; each question costs the author a round trip. Batch. |
| "It's a one-line fix, I'll just make it while I'm here" | Editing while planning is the one thing this phase forbids. Classify it bounded and `proceed`; the edit is thirty seconds away. |
| "I understand this kind of app, so it's bounded" | Bounded measures the repo, not you. If the flow you would change is not here to read, it is an outline. |
| "The outline is obvious, I'll proceed and describe it in the note" | An obvious outline is a short one. Hand it off; Proceed is the author's decision when your role asks for it. |
| "I need to prototype to know what to ask" | Minions prototype in scratch space and report. Your tree stays clean. |

## Red flags

- An edit tool call before Proceed
- A second `yield --question` in one planning phase
- `proceed` on a brief that names a subsystem which does not exist yet

## Checklist

- [ ] Classified: spike, bounded, or outline — and said which in your yield or your `proceed --note`
- [ ] Read what you need; minions for anything that would fill your context
- [ ] Spike: handoff with the answer · Bounded: `proceed --note` · Outline: one question yield, then the outline handoff
- [ ] Turn ended with the ball where it belongs
