# Working on zharn

Read [README.md](README.md) first, then [docs/DESIGN.md](docs/DESIGN.md). This file covers only
where documents go — everything else is in those two.

## The docs tree

```
docs/
  DESIGN.md              the program: stack, architecture, window model, licensing
  AGENT-MODEL.md         the story model — what it is and why
  specs/                 how the program ought to be
  design/mockups/        rendered UI mockups (build.py + headless Chrome)
  superpowers/
    proposals/           the change we agreed to make
    plans/               the steps that make it
```

Three kinds of document, and the difference is tense:

| | tense | lifespan |
|---|---|---|
| `docs/specs/` | present — how the program *is* | standing; revised in place |
| `superpowers/proposals/` | future — how the code is *going to change* | expires when the change lands |
| `superpowers/plans/` | future — the ordered steps | expires when the change lands |

A **spec** describes the program as it ought to be, and wins over the code: where they disagree,
the code is wrong. Nothing in a spec should be phrased as work to do. No migration sections, no
"X is renamed to Y", no old-to-new vocabulary tables — this project has no backward compatibility
(DESIGN.md §0), so when the model changes, rewrite the spec in the present tense and delete what
it replaced.

A **proposal** and its **plan** are scaffolding for one change. They are dead as soon as the
change ships; leave them where they are, stale paths and all, and don't spend edits keeping them
current.

## Where to write

- Brainstorming a change → `docs/superpowers/proposals/YYYY-MM-DD-<topic>.md`
  (this overrides the superpowers skill's default of `docs/superpowers/specs/`)
- Planning one → `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`
- Describing how the program ought to be → `docs/specs/<topic>.md`

**Graduation.** A proposal that stops describing a change and starts describing how the program
works — you find yourself revising it after the change shipped, or citing it as the authority on
current behaviour — belongs in `docs/specs/`. Move it, drop the date from the filename and the
title, rewrite it in the present tense, and add it to DESIGN.md's summary sections.

Specs carry code blocks only to declare a shape: a state schema, a record, a directory tree, a
verb surface. A code block that carries a file body for someone to paste belongs in a plan.
