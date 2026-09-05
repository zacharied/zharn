# Approve fast-forwards the branch: the cast integrates, the harness moves the ref

*Proposal, 2026-09-05. Expires when it lands; the standing text goes into
`docs/specs/workspace-model.md` (§4.2, §4.6, a new §4.8, §8, §9, §10),
`docs/specs/story-lifecycle.md` (§2.1 Approve, §2.2 handoff, §7, §8), `DESIGN.md` §8, and
`harness/skills/skills/implementing-a-story/SKILL.md`.*

Every story works on its own branch in its own worktree, cut from its parent environment's
branch, and its work "reaches its author only through a handoff and Approve" (workspace spec §4).
Today Approve writes a system comment, resolves the threads, retires the cast and marks the
story done. The branch stays where it was. The author merges by hand, which is the one thing the
handoff gate was built to make unnecessary. This is the last piece designed as a gap on the path
to self-hosting (DESIGN.md §8 item 8): with it, a story in Scratch against the zharn repo lands in
the checkout the harness is running from.

## Positions taken

| # | Question | Position |
|---|---|---|
| 1 | Does the harness merge, or fast-forward only? | Fast-forward only. The commit that lands is the commit the checks ran on. A merge commit made by the harness was never tested, and the harness process never waits on a test suite (workspace spec §4.6). |
| 2 | Who brings the branch up to date with its target? | The cast, before the handoff. Rebase by default; merge the target in when a rebase gets ugly. The gate needs ancestry, not a method. |
| 3 | Is "behind the target" checked at handoff or only at Approve? | Both. At handoff the cast is told before the author reads anything. The target can still move between handoff and Approve; then Approve refuses the same way and the author replies. |
| 4 | Is there a flag past the ancestry gate? | No. Like the tree gate: it protects the work, not its quality. |
| 5 | Must the target's worktree be clean? | No rule beyond git's own. A fast-forward that would overwrite dirty files is refused by git and the Approve is refused with that message; one that touches other files goes through. The parent character running `approve` is the one who dirtied the tree, and reads the refusal. |
| 6 | Does Approve run in the harness process or in a character's turn? | The harness process. A human Approve has no turn to ride. A fast-forward is a local ref update plus a checkout; it is bounded by `GIT_TIMEOUT_S` like clone and setup. |
| 7 | Is the worktree removed? | Yes, once no character is still finishing a turn in it. The branch is kept. |
| 8 | Does Cancel clean up? | No. Nothing was validated; Reopen may want the tree. A general prune is a later verb. |
| 9 | Pull requests? | Out of scope. The per-environment integrate step is one function so it can grow one later. |

## 1. Vocabulary

A story's environment has a **target**: the branch of its parent environment. For a root story
that is the repo's `base`; for a sub-story it is `zharn/<parent-key>`. The story page already
prints it as "into main". The environment record already holds it as `parent` (null meaning the
main checkout and `base`). Nothing new is stored.

A branch is **up to date** with its target when the target's tip is an ancestor of the branch's
tip: `git merge-base --is-ancestor <target> <branch>`. That is the whole condition; whether the
cast got there by rebasing or by merging the target in is its own business.

## 2. The ancestry gate at handoff

Workspace spec §4.6 gains a third gate between the tree and the checks:

**The tree, then the target, then the checks.** At a handoff on the main thread of an
`implementing` story, after the tree gate passes, the CLI checks each environment's branch
against its target. A branch that is not up to date refuses the handoff:

```
handoff refused: zharn/SCR-3 is 2 commits behind main in zharn — rebase onto main (or merge it in) and retry
```

The count is `git rev-list --count <branch>..<target>`. No flag past it. Side threads are not
gated, as with the tree. It is a check on branches, not trees, so it runs in the repo's main
checkout and an environment whose worktree directory is gone is still gated; the `env.checks`
plan carries each environment's target and repo path for it.

Why before the checks and not after: the checks are the expensive gate, and a rebase changes
what they would have measured.

## 3. Approve

Story lifecycle §2.1, the Approve row, becomes:

> **Approve `[note]`** — precondition `(implementing, author)` **and every environment of the
> story fast-forwards into its target** (workspace spec §4.8). Effect: each environment's target
> is moved onto the story branch's tip; the system comment carries the result; every open thread
> resolves, main included; every character retires at its next turn boundary; worktrees are
> removed as the cast retires. → `(done)`.

A story is never done with unmerged work. The store does, in order:

1. **Lifecycle precondition.** `step(story, Approve)` is run for its rejection only; nothing is
   persisted yet.
2. **Precheck every environment.** The repo is present (a missing repo refuses with the §3.3
   message); the branch is up to date with its target. Any failure refuses the whole Approve
   with one line per failing environment. Nothing has moved.
3. **Integrate each environment**, in registration order. If the target branch is checked out
   in some worktree of the repo (`git worktree list --porcelain`), run
   `git merge --ff-only <branch>` in that worktree, so its files update. Otherwise move the ref:
   `git branch -f <target> <branch>`. A target already at the branch's tip is a no-op.
4. **Persist** the reducer's output; the system comment's body is `approved` (plus the note)
   followed by one line per environment:

   ```
   approved
   merged zharn/SCR-3 → main in zharn (a1b2c3d..e4f5a6b, 4 commits)
   merged zharn/SCR-3 → main in client (no changes)
   ```

   and `structured.merged = [{repo, branch, target, from, to, commits}]`, the way checks ride a
   handoff.

If step 3 fails partway (git refuses the fast-forward in a dirty target tree, or times out),
the Approve is refused with git's message and the story stays `implementing`. Repos already
fast-forwarded stay fast-forwarded; a retry finds them up to date and moves on. Approve is
therefore idempotent and safe to repeat.

A story with no environments approves with no git at all. An environment whose story committed
nothing fast-forwards as a no-op and reports `(no changes)`.

### 3.1 The two kinds of target

**A root story's target is `base`**, usually checked out in the main checkout — the tree the
author stands in and, for the zharn repo in Scratch, the tree the harness is running from. The
fast-forward updates that tree; the reloader sees the files change and hot-reloads, or shows
*restart required* when a class changed shape. That is the bootstrap moment. When the main
checkout is on some other branch, only the ref moves.

**A sub-story's target is `zharn/<parent-key>`**, checked out in the parent story's worktree,
where the parent's cast may be mid-work. Its files are fast-forwarded under it; the actor is
the parent character running `approve <key>`, so it knows. Git refuses a fast-forward that
would overwrite uncommitted changes, and that refusal is the Approve's refusal: the character
commits or sets aside its own work and retries. When the human acts as author on a
character-owned sub-story (§2.3), the system comment is delivered to the owning character as
today, and now names what landed in its tree.

### 3.2 Cleanup

At Approve, and at every turn end of a done story, an environment whose story has no character
with a live working context is removed: `git worktree remove --force <path>`; the record is
kept as it is, plus `removed: <time>`. The branch is kept: it is the story's history, and
Reopen needs it.

**Reopen** changes nothing here. `env open` already re-adds a worktree on the existing branch
and re-runs `setup` (§4.4). The branch is behind its target by whatever landed since, and the
ancestry gate makes the cast rebase before its next handoff.

**Cancel** leaves environments as they are.

## 4. Skill

`implementing-a-story` step 6 becomes:

> Before the handoff: `zharn:verification-before-completion`, then commit in your environment
> and bring your branch up to date with its target (`$HARNESS_CLI env list` names it): rebase
> onto it, or merge it in if the rebase fights you. Run the repo's checks yourself first; a
> refused handoff is a wasted turn.

The handoff section gains: "A branch behind its target is refused like a dirty tree, and there
is no flag past it either." One rationalization row:

| "I'll leave the rebase to the author" | Approve only fast-forwards. A branch behind its target cannot be approved; the author's only move is to send it back to you. |

The checklist gains "Branch up to date with its target".

## 5. CLI and UI

`zharn story approve <key>` (a character approving its sub-story) prints the merged lines, one
per environment, then the same rejection text as the store on refusal.

`zharn env list` gains the target per environment (`into main`), so the skill can point at it.

The story page needs nothing new: the Approve system comment shows the merged lines like any
system comment, and a refused Approve reports through the action's `@intent` to the status bar
like every refused author action. Removed environments drop out of the story page's list and
the workspace page's worktree column.

## 6. Where it lives

`harness/environments.py` gains `target(rec)`, `behind(rec) -> int`, `integrate(rec) -> dict`
(one environment: precheck, fast-forward in the right place, return the merged record) and
`remove(rec)`. `harness/stories.py: approve` orders steps 1–4 above and hands the merged
records to the reducer's note; the retirement sweep in `_on_turn_end` calls `remove` for a done
story's environments once no context is working. `harness/cli.py` gains the ancestry gate
beside `dirty_trees`, and `env list` prints the target.

## 7. Tests

All against real temporary git repositories; no network.

* `tests/test_environments.py`: `behind` counts; `integrate` fast-forwards a root branch into
  `base` checked out in the main checkout (files update) and into `base` checked out nowhere
  (ref moves, tree untouched); a sub-story into its parent's worktree with a clean tree, with
  dirty non-overlapping files (goes through, files kept), with dirty overlapping files
  (refused with git's message, nothing moved); a branch with no commits is a no-op reporting
  `(no changes)`; `remove` deletes the worktree, keeps the branch and the record.
* `tests/test_stories.py`: Approve on a story whose base moved after the handoff is refused and
  the story stays `implementing`; two repos with one behind moves nothing; a partial failure
  leaves the merged repo merged and a retry completes; the system comment's body and
  `structured.merged`; a story with no environments approves as today; a missing repo refuses;
  the worktree is removed at Approve when no character is working and at the turn end of the
  one that was; Reopen after Approve re-adds the worktree on the kept branch and its next
  handoff is refused as behind until rebased.
* `tests/test_cli.py`: the ancestry gate refuses an implementing main handoff with the target
  and count named, before the checks run; `approve <key>` prints the merged lines; `env list`
  shows the target.
* `tests/test_ui_story.py`: the Approve comment's merged lines render; a removed environment
  leaves the list.

## 8. Out of scope

Pull requests and pushes. A prune verb for canceled stories' worktrees. Re-running checks after
a target moves (the cast rebases and hands off again; that is the design). Moving the
fast-forward out of the harness process into a turn (the same follow-up as clone and setup).
Squashing a story's commits on landing.
