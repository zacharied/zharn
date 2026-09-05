# Context usage: the meter, the two lines, and compaction off

*Proposal, 2026-09-04. Expires when it lands; the standing text goes into
`docs/specs/story-lifecycle.md` (§2.3, §3.4, §5.3, §8) and `docs/DESIGN.md` §8 item 3.*

The characters-and-delivery plan deferred context-usage tracking, and with it the two rows of the
mechanics table that depend on it: the recap nudge at `CONTEXT_WARN` and the auto-recast at
`CONTEXT_MAX`. The spec names both knobs as fractions of the window; neither exists in
`config_def.py`. Meanwhile every context the harness spawns is compacted by Claude Code on its own
schedule, which is the thing the recap/recast ladder was designed to replace.

The measurement itself is nearly free. What this proposal decides is what the number means, when the
harness acts on it, and how the character is told.

## What the CLI actually reports

Verified against `claude` 2.1.259 on 2026-09-04 (one Haiku turn, `--output-format stream-json`):

* Every `assistant` event carries `message.usage` with `input_tokens`, `cache_read_input_tokens`,
  `cache_creation_input_tokens` and `output_tokens`. The first three sum to the size of the
  context on that API call. A bare "say pong" already sits at 21,874: the system prompt, tools and
  skills are in there. One API message produces one `assistant` event per content block, each
  repeating the same `usage`.
* The `result` event carries `modelUsage[<model>]` with `contextWindow` (200,000 for Haiku,
  1,000,000 for the current tier) and `maxOutputTokens`. The window is unknown until the first
  result.
* Auto-compaction is on by default, emits `{"type": "system", "subtype": "compact_boundary"}`, and
  is switched off by `DISABLE_AUTO_COMPACT=1` in the environment (`--autocompact <tokens>` sets its
  window instead).

So context usage is a reading, not a sum: the input side of the most recent call. Output tokens of
one call join the input of the next. Minions' calls are their own contexts and never count.

## Positions taken without a ruling

Each was put to the author and not contested, or follows from what was.

| # | Question | Position |
|---|---|---|
| 1 | Is compaction off for bare contexts and asides too? | Yes. One environment for every spawn. A bare context promoted into a story would otherwise carry a compacted history under a truthful-looking meter. |
| 2 | Does a `compact_boundary` event get handled? | It is never expected. If one arrives, the interpreter appends an error row so it is visible, and nothing else. |
| 3 | Is recap freshness measured in tokens now? | No. The ladder keeps `RECAP_STALE_TURNS`. With 200K of headroom between warn and max, a recap posted at the warn line is nearly always fresh at the max line. |
| 4 | Does a recap clear the meter? | No. Nothing shrinks a context but recast. A recap clears `recap due`; the number stays where it is until the max line recasts. |
| 5 | Does the situation line carry the number? | No. Only `recap due`, when it is. The number is the author's, on the cast panel. |
| 6 | Do the thresholds fire once or every turn? | Once per context, each. They reset with the context on recast, and a fork inherits its source's numbers but not its crossings. |

## 1. Measurement

`StreamInterpreter` (`harness/agents.py`) keeps two more numbers beside cost and turns:

```
context_tokens   int   input + cache_read + cache_creation of the latest assistant event; replaced, never summed
context_window   int   modelUsage[*].contextWindow from the latest result; 0 until the first result
```

Both rebuild on replay for free, since replay already feeds the log back through the interpreter.
A forked context copies `context_tokens` and `context_window` from its source at creation, so the
meter is right before its first call; a recast starts at zero.

`Context.summary()` gains `contextTokens` and `contextWindow`. That is the whole surface the UI
needs: the cast panel and the contexts list already read the summary.

## 2. Compaction off

`Context._env()` sets `DISABLE_AUTO_COMPACT=1` for every spawn. The only way a character's memory
shrinks is the ladder (§3.4), and the meter is truthful for the life of the context. The spec's
out-of-scope line, "provider-side compaction (recast supersedes it)", becomes a mechanism: it is
superseded because it is off.

## 3. Thresholds

Two knobs in `config_def.py`, in tokens, not fractions:

```
CONTEXT_WARN = 300_000   # recap nudge
CONTEXT_MAX  = 500_000   # recast at the turn boundary
```

These are for a 1M window. When the model's window is smaller than `CONTEXT_MAX` plus its output
reserve, both scale by the window's ratio to 1M: Haiku's 200K gives 60K and 100K from the same two
numbers. Until the first result the window is unknown and the thresholds apply unscaled; the first
turn of a small-window model cannot cross them anyway.

## 4. The two crossings

The story store hears every context change and compares the character's `context_tokens` against
the effective thresholds. Each crossing is recorded once on the character, with the context's turn
count at the time:

```
Character.context_warned   int | null   turns when CONTEXT_WARN was crossed on this context
Character.context_maxed    int | null   turns when CONTEXT_MAX was crossed on this context
```

Both are cleared by recast. Neither is derived: a recap does not lower the number, so "already
warned" cannot be recomputed from it.

**Warn.** A message is pushed into the context now, mid-turn, by the path a steering comment takes:

```
[situation] … · recap due
[harness] context past the warn line: post a `recap` in #<attended> now — your successor is
built from the story record and that recap.
```

From then on every situation line ends with `· recap due` until a recap newer than the crossing
lands (`recap_turns ≥ context_warned`), which is the only thing that clears it.

**Max.** A second push, then the character is marked for recast through the pending-recast path
that already serves a working character, so the recast fires at the turn boundary:

```
[harness] context at the limit: finish the step in hand and post a `recap` in #<attended> now.
You are recast when this turn ends.
```

The ladder picks the rung as today, and the system note in the main thread says why:
`recast <name> as <role> (context; rung 1: fresh recap)`.

A turn that ignores both and runs into the real window ends with an API error, which is a turn end
like any other: the quiet check posts on the character's behalf and the pending recast fires.

## 5. Spec changes

`docs/specs/story-lifecycle.md`:

* §2.3, the two threshold rows: tokens not fractions, the pushed message at each crossing, the
  `recap due` marker, once per context.
* §3.4: `context_warned`/`context_maxed` cleared by recast; the system note names the cause.
* §5.3: the situation line gains an optional trailing `· recap due`.
* §8: drop "provider-side compaction"; it is off, not out of scope.
* §1: the two new `Character` fields; `Context` gains nothing durable (the numbers are derived from
  the log).

`docs/DESIGN.md` §8 item 3: the deferred note on context-usage tracking goes.

## 6. Tests

* `tests/test_stream_interpreter.py`: `context_tokens` from a hand-built `assistant` event, the
  same event twice leaving it unchanged, `context_window` from a `result`, both surviving replay.
* `tests/fake_claude.py`: emits `usage` on assistant events and `modelUsage` with a window on
  results; a prompt containing `tokens=<n>` sets the next reading, so store tests drive crossings
  without money.
* `tests/test_stories.py`: warn pushes once and only once; `recap due` appears on the next
  delivery and clears after a recap; max marks a recast that fires at turn end with a note naming
  the cause; a fork inherits the numbers and not the crossings; recast clears both.
* `tests/test_contexts_unit.py`: `DISABLE_AUTO_COMPACT` in the spawn environment;
  `compact_boundary` becomes an error row.
* `tests/test_ui_cast.py`: the summary reaching the panel carries `contextTokens`. The visual
  meter is a separate piece of work.
