# Workspaces, repos, environments

Fixes the model *around* stories: where stories live, what a repo is to zharn, where a
character stands when it works, and where all of it is stored. Complements
[`docs/AGENT-MODEL.md`](../AGENT-MODEL.md) (which says nothing about directories) and the
[story lifecycle spec](story-lifecycle.md). Where code disagrees with this document, the code is
wrong.

*Written 2026-08-31; environments revised 2026-09-03.*

## 1. Concepts

Two words are new to zharn's vocabulary, one is kept from bb, and one from bb is dropped.

| concept | one line | cardinality |
|---|---|---|
| **workspace** | a directory with a `.zharn/`; owns a board, a story-key prefix, and a set of repos. The thing you open on the start screen. | n repos, n stories, n contexts |
| **repo** | a registered git repository: path, name, and the settings the harness needs mechanically | 1 git repository; may be registered in several workspaces |
| **environment** | a checkout of one repo where a context stands: the **main checkout** (the registered path) or a **managed worktree** | 1 repo; hosts n contexts |
| **story** | as in AGENT-MODEL — rooted at a workspace | 1 workspace; 0..n environments, at most one per repo |
| **context** | as in AGENT-MODEL | 0..1 environment; none → its cwd is the workspace dir |

**Scratch** is not a concept: it is the workspace zharn creates on first run in appdata (§2.2).
**Board** is not an object: it is a workspace's stories viewed by phase.

Why "repo" and not bb's "project": a project would be 1:1 with a git repository by definition,
which makes one of the two words redundant, and "project" is the word a board will eventually
want for a *group of stories*. Why stories are workspace-rooted rather than repo-rooted: most
real work spans repositories (API + client in one review) or none at all (research, docs); a
story's repos are *derived* from where its cast chose to work (§4.3), never declared as its home.

Consequences for what DESIGN.md previously kept from bb: story keys carry **one prefix per
workspace**, not per project; there is no auto-created "Inbox" project — a story with no repos
is simply a story.

## 2. Workspace

### 2.1 Identity

A workspace has three identifiers, each with one job:

* **id** — a UUID minted at creation, stored in `workspace.toml`. Identity across moves and
  renames; the only key anything outside the workspace dir (appdata) may use. Nothing is ever
  keyed by path: the same directory has three spellings on a Windows-GUI / WSL-agents machine.
* **prefix** — short, upper-case, appears in story keys (`ZH-12`). Defaults from the folder name.
  Changing it is a rename: existing keys are kept as aliases (§5.2), new stories get the new prefix.
* **name** — display only. Defaults from the folder name.

The workspace directory is a *home* for state, not a container for repos: registered repos may
live anywhere. Repos inside the workspace dir are stored as paths relative to it; repos outside as
absolute paths (supported, but portability is then the user's problem — a moved workspace keeps
its inside repos and reports outside ones as *missing*, §3.3). Nested workspaces are independent:
opening a directory reads only that directory's own `.zharn/`.

### 2.2 Scratch

On first run zharn creates an ordinary workspace at `<appdata>/zharn/scratch/` named **Scratch**,
prefix `SCR`, and registers zharn's own source checkout as the repo `zharn` in it (fork-as-config:
"change the harness" is one story away from anywhere). Scratch is pinned first on the start screen
and cannot be deleted; it is otherwise indistinguishable from any workspace and **no code may test
for it**. It is the home of everything that exists before it has a home: bare contexts started
from the start screen, one-off stories, stories about zharn itself. Stories leave Scratch by
being moved (§5.3).

Scratch is the workspace zharn opens when `HARNESS_WORKSPACE` is unset. `<appdata>` is the
platform application-data directory (`%APPDATA%` on Windows, `$XDG_DATA_HOME` or
`~/.local/share` elsewhere); `ZHARN_APPDATA` overrides it, which is how tests keep it in a temp dir.
`ZHARN_APPDATA` names zharn's own data directory (there is no wider "appdata" concept it plugs
into); Scratch lives at `$ZHARN_APPDATA/scratch`.

## 3. Repos

### 3.1 Registration record

```
[[repos]]
name   = "client"          # unique within the workspace; defaults from the directory name
path   = "../client"       # relative to the workspace dir if inside it, else absolute
checks = "npm test"        # run in a story's environment for this repo at every implementing handoff
setup  = ".zharn-env-setup.sh"   # optional; run once in every new managed worktree
base   = "main"            # branch managed worktrees are created from; default: the repo's HEAD branch at registration
```

Checks are per repo, run per environment (§4.4). `checks` and `setup` are bash lines: the harness runs each as
`bash -c <line>` in the environment directory — the system bash on POSIX, Git Bash on Windows — so one string
serves every checkout of a committed `workspace.toml`. A multi-command line uses bash syntax (`&&`, `;`, …).
`config.BASH_PATH` names the interpreter; unset, it is `bash` on PATH on POSIX and, on Windows,
`CLAUDE_CODE_GIT_BASH_PATH` or Git for Windows' `bin\bash.exe` beside the `git` on PATH (never System32's
`bash.exe`, which is WSL). The same bash is pinned into every Windows character's Claude Code
(`CLAUDE_CODE_GIT_BASH_PATH`, PowerShell tool off), so the shell a character types into and the shell its
checks run in are one. No bash is a refused handoff or a failed `env open` whose message names Git for Windows.

### 3.2 Who registers

Registration is how a character obtains the harness's *help* (environments, checks, Approve),
not a permission gate — a context is a shell and may `cd` anywhere; but worktrees, handoff checks
and Approve exist only for registered repos.

* **The author** registers from the workspace page or the start screen (§7).
* **Any character** may register a repo from inside a story: `zharn repo add <path | url>`. A
  path is registered as is; a URL is cloned into `<workspace>/repos/<name>/` and registered
  relative. A clone is a network + file write and is subject to the character's permission
  ceiling like any other; roles that cannot write cannot register.
* Every registration is recorded as a **system comment in the thread the character is
  attending** ("Registered repo `client` at `../client`"), so workspace-shape changes are part of
  the story record and visible on the board without a separate channel.
* **Unregistering is author-only** (UI). It never deletes files; managed worktrees of that repo
  are left in place and the repo's stories keep working the moment it is registered again.

### 3.3 Missing repos

A registered path that no longer exists (moved, unmounted, absolute path from another machine)
is shown as *missing* with a **Relocate** action; contexts that need it fail with that message.
Nothing is deleted or rewritten automatically.

## 4. Environments

*Revised 2026-09-03: every story works on its own branch, in its own worktree, cut from its parent
environment; the parent environment of a root story is the main checkout, and no story ever works
there. One rule: friends share a tree, stories get a branch. A story's work reaches its author
only through a handoff and Approve, which fast-forwards the story's branch into its parent
environment's — that is what makes the handoff mean something.*

### 4.1 Kinds

* **Main checkout** — the registered path itself. Where bare contexts stand. Never created or
  destroyed by zharn, and never worked in by a story: it is the root of every parent chain, the
  branch point, not a place of work.
* **Managed worktree** — created by zharn with `git worktree add` under
  `<workspace>/.zharn/local/worktrees/<repo>/<story-key>/`, on the new branch `zharn/<story-key>`
  cut from the parent environment's branch (§4.2). `setup` runs once after creation, in the
  worktree. This is the only kind of environment a story has.

### 4.2 The parent chain

Every story has, per repo, a **parent environment**: for a root story it is the main checkout;
for a sub-story it is its parent story's environment for that repo, created on demand if the
parent has none yet, because the sub-story's work is the parent's work. A story's environment for
a repo is its own managed worktree, branched from the parent environment's branch: at the root
that is the repo's `base`; under a parent story it is `zharn/<parent-key>`, so a sub-story starts
from the parent's committed work and its results return to the parent's branch through Approve.

Why no way to stand in the parent's tree, and no way to work on the main checkout: either would
put a story's work where its author stands before the author validated a handoff, and would have
two casts editing one working tree. A character that wants someone working in *its* tree calls a
friend; a character that wants contained, validated work creates a sub-story. The environment
boundary is the story boundary. A story that only investigates still gets a worktree — cheap, and
one rule.

The parent environment's branch is the story's **target** — the repo's `base` for a root story,
`zharn/<parent-key>` for a sub-story — and Approve fast-forwards the target onto the story's
branch (§4.8).

### 4.3 Records

`local/environments.json` holds one record per `(story, repo)` pair:

```
{story, repo, path, branch, parent, created, setup_done}
```

`removed` is set when the worktree was removed after Approve (§4.8); such records are not
environments of the story until `env open` revives them.

`parent` is the `(story, repo)` of the parent environment, or null when the parent is the main
checkout — the merge target, and where the branch was cut from. The story's `repos` list is the
set of records that exist; it is derived, persisted in `story.json` for the board filter, and
never edited by hand. An author may add a repo *hint* at creation for scoping; a hint is not an
environment.

### 4.4 Lazy acquisition

A story starts with no environments. `zharn env open <repo>` is idempotent per pair: the first
call resolves the parent chain (creating parent environments as needed), creates this story's
worktree, and every later call returns the same environment — one per pair, shared by the
whole cast, so a reviewer friend sees the implementor's work. The command prints the
environment's path and records the environment on the calling character (§4.5).

* A worktree record whose directory is gone (deleted by hand) is pruned with `git worktree
  prune` and re-added on its existing branch. A re-added worktree is a new worktree: `setup`
  runs again.
* A failed `setup` leaves the worktree in place, returns the error to the caller, and is retried
  on the next `env open`; `setup_done` records success.
* A missing repo (§3.3) fails with the missing message and creates nothing.
* Git errors (branch exists, worktree registered elsewhere) are reported as is.

### 4.5 Context placement

A context's working directory is decided at every spawn, not at creation, so a character may
move between environments *of its story* between turns by calling `env open` again. The rules:

* A character's context runs in its environment's path, else the workspace dir.
* Minions inherit the process directory through the provider's native agent tool.
* A friend cast by `call` (fresh or `--fork`) starts in the caller's environment.
* A recast keeps the character's environment.
* The protagonist starts in the workspace dir.

Processes receive `HARNESS_WORKSPACE` (dir), and, when the character has an environment,
`HARNESS_REPO` (name) and `HARNESS_ENV` (path).

### 4.6 The gates at a handoff: the tree, the target, then the checks

**The tree first.** At a handoff on the main thread of an `implementing` story, the CLI runs
`git status --porcelain` in every environment of the story. Any output — modified, staged or
untracked files alike — refuses the handoff and prints it per repo: "handoff refused: uncommitted
changes in fixture — commit them and retry". There is no flag past it: a story's work reaches its
parent branch through Approve, which merges the story's branch, and what is not committed is not
in the story. Side threads are not gated; friends share the protagonist's tree, and the
protagonist's main handoff is where the work is declared done.

**Then the target.** The story's branch must contain its target's tip — nothing on the target
the branch lacks (`git rev-list --count <branch>..<target>` is zero): the cast rebases onto the
target, or merges it in, before handing off. A branch behind is refused with the target and the
count named — "handoff refused: zharn/SCR-3 is 2 commits behind main in zharn — rebase onto main
(or merge it in) and retry" — and there is no flag past it either: Approve only fast-forwards
(§4.8), so a branch behind cannot land. Every environment behind is named, and the closing advice
names every distinct target ("… — rebase onto main, release (or merge it in) and retry"). The
gate fails closed: a comparison git cannot make — a bad ref, a repo it cannot read — refuses the
handoff naming the repo and git's own words ("handoff refused: cannot compare zharn/SCR-3 with
main in zharn: <what git said>"), never read as up to date. It is a check on branches, so it runs
in the repo's main checkout whether or not the worktree still exists. It runs before the checks
because a rebase changes what they measure.

`checks` is per repo (§3.1). At a handoff on the main thread of
an `implementing` story, the CLI — inside the character's turn, so the harness process never
waits on a test suite — lists the story's environments, runs each repo's `checks` in that
environment, and attaches `[{repo, cmd, exit, output}]` to the handoff comment. Output is
truncated to `config.CHECKS_OUTPUT_LIMIT` characters. A repo with no `checks` contributes
nothing.

What a failing check does is a knob, `config.HANDOFF_CHECKS`, because the trade is token burn
against red handoffs:

* `"gate"` (default) — the handoff is refused, the failures are printed to the character, and
  the character fixes and retries; `--despite-checks` posts the handoff anyway with the results
  attached.
* `"attach"` — the handoff always posts, results attached; the author sees the red.

### 4.7 Collisions

The same repo registered in two workspaces means both create worktrees in one `.git`. Branch
names collide only if both workspaces share a prefix *and* a story number; zharn does not defend
against this beyond reporting the git error. Choose distinct prefixes.

### 4.8 Approve

Approve fast-forwards every environment of the story into its target and is refused when any
cannot: a story is never done with unmerged work. The commit that lands is the commit the checks
ran on; the harness never creates a merge commit and never runs checks itself.

In order, in the harness process (bounded by `GIT_TIMEOUT_S`):

1. The lifecycle precondition `(implementing, author)`.
2. Every environment prechecked: the repo present (§3.3), the branch up to date with its target.
   One failing environment refuses the whole Approve; nothing has moved.
3. Each environment fast-forwarded, in the order the story acquired them. When the target branch
   is checked out in a worktree of the repo, the fast-forward runs there so its files update;
   otherwise the ref alone moves. A target already at the branch's tip is a no-op.
4. The Approve system comment carries the result — `approved`, then one line per environment,
   `merged zharn/SCR-3 → main in zharn (a1b2c3d..e4f5a6b, 4 commits)` or `(no changes)` — and
   `structured.merged = [{repo, branch, target, from, to, commits}]`.

A refusal partway (git refuses to overwrite dirty files in the target's tree; a timeout) is the
Approve's refusal with git's message; the story stays `implementing`, repos already
fast-forwarded stay so, and the next Approve finds them up to date and finishes. A story with no
environments approves with no git at all.

**The two kinds of target.** A root story's target is `base`, usually checked out in the main
checkout — the author's own tree and, for zharn in Scratch, the tree the harness runs from; the
fast-forward updates it and the reloader takes it from there. A sub-story's target is
`zharn/<parent-key>` in the parent's worktree, where the parent's cast may be mid-work: the
actor is the parent character running `approve <key>`, and git's own rule applies — a
fast-forward that would overwrite its uncommitted files is refused, one that touches other
files goes through.

**Cleanup.** At Approve, and at every turn end of a done story, once no character of the story
has a live working context, each environment's worktree is removed (`git worktree remove
--force`); the record stays, stamped `removed`, and the branch stays — it is the story's history.
Reopen changes nothing here: `env open` re-adds the worktree on the kept branch and runs `setup`
again (§4.4); the branch is behind by whatever landed since, and the ancestry gate makes the cast
rebase before its next handoff. Cancel leaves environments as they are.

## 5. Stories in a workspace

### 5.1 Keys

`<prefix>-<n>`; `n` is a per-workspace counter in `workspace.toml`. Mentions (`@ZH-12`) resolve
within the workspace, including aliases.

### 5.2 Aliases

`story.json.aliases` lists every key the story has had. Aliases resolve everywhere a key does.
Sources of aliases: prefix rename (§2.1), story move (§5.3).

### 5.3 Move

**Move story to workspace** is an author action, allowed in any phase (restricting it to
backlog/todo would block exactly the case that matters: a Scratch story that grew). Effect:

1. The story directory is moved; the story gets the destination's next key; the old key is
   appended to `aliases`.
2. For each of the story's environments: if the destination has the same repo registered
   (same resolved path), the worktree record moves with it; otherwise the move offers to register
   the repo in the destination, and declines to move until the author decides.
3. Contexts are machine-local files and move under `local/`.

Sub-stories move with their parent.

## 6. Storage

```
<workspace>/
  .zharn/
    workspace.toml            id, name, prefix, next, repos[]
    stories/<key>/
      story.json              title, description, priority, phase, author, protagonist, main_thread,
                              parent_story, aliases[], repos[], hint_repos[], created
      threads.jsonl           append-only: threads, comments, yields, recaps, registrations, transitions
    local/                    machine-local; a generated .zharn/.gitignore ignores it
      contexts/<id>.jsonl     transcripts; provider session ids (resumable only on this machine)
      characters.json         live_context, attention, inbox per character
      environments.json       (story, repo) → {path, branch, parent, …} (§4.3)
      worktrees/<repo>/<key>/ managed worktrees
      session.json            layout, open tabs
  repos/                      exists only if something was cloned by URL
```

Durable vs local: the durable record is small text and is the complete history of the work
(comments are the only channel), so a moved folder carries everything that matters and the record
is *committable* if a team wants shared history — append-only JSONL keeps that merge-friendly.
This spec does not build sharing; it only refuses to foreclose it. `local/` moves to
`<appdata>/zharn/local/<workspace-id>/` only if a workspace dir proves unable to hold it (synced
folders); it is then keyed by id, never by path.

Appdata (`<appdata>/zharn/`) holds: `scratch/` (a full workspace, layout above) and
`recents.json` (`[{id, path, name}]`). Nothing else. Re-opening a moved workspace by folder
re-binds the recent entry by id.

Agent processes receive `HARNESS_WORKSPACE` (dir), `HARNESS_REPO` and `HARNESS_ENV` (§4.5) in
addition to the existing variables.

## 7. Start screen and opening a folder

The start screen lists **Scratch** (pinned), recents, and **Open folder…**. Opening a folder:

* it has `.zharn/` → open it;
* it does not → create a workspace: name and prefix prefilled from the folder name, editable;
  if the folder is a git repo, register `.`; if it contains git repos one level down, offer them
  checked. Nothing is written until the user confirms.

Inside a workspace: a **workspace page** (repos with status and Relocate/Unregister, prefix and
name), the board, contexts, and **Move story** on every story page.

## 8. CLI

Inside a character (existing `zharn story …` verbs unchanged, plus one flag):

```
zharn story yield --handoff --body B [--despite-checks]   # §4.6
zharn repo add <path|url> [--name N] [--checks C] [--setup S] [--base B]   # §3.2; system comment
zharn repo list [--json]
zharn env open <repo>                 # prints the environment path; creates it on first use (§4.4)
zharn env list [--json]               # this story's environments, each with its repo's checks and its target
```

Author-only, UI (and CLI when the author is a character, for sub-stories):
`story move <key> --to <workspace-id|path>`, repo unregister and relocate, prefix rename.

## 9. Tests

All against real temporary git repositories; no network.

* `tests/test_workspace.py`: create/open; relative vs absolute repo paths; `repo add` by URL
  clones from a local path into `repos/<name>/`; `base` defaults to the HEAD branch at
  registration; folder inspection (repo at `.`, repos one level down); missing repo detection and
  relocate; prefix rename keeps aliases; Scratch created on first run under `ZHARN_APPDATA` with
  the zharn checkout registered, and never special-cased (grep the source for `scratch` outside
  its creation).
* `tests/test_environments.py`: `env open` is idempotent per `(story, repo)`; branch and path
  naming; a root story branches from the repo's `base`; a sub-story branches from
  `zharn/<parent-key>` and creates the parent's environment on demand; a grandchild branches from
  its parent's branch; `setup` runs once and is retried after failure;
  a deleted worktree directory is recreated on its branch; a missing repo fails and creates
  nothing; the derived `repos` list; cwd at spawn for a character, a called friend, a fork, and a
  recast; `HARNESS_REPO`/`HARNESS_ENV`; `target` and `behind`; `integrate` into a checked-out base
  and into one checked out nowhere, into a parent's worktree clean, dirty elsewhere, and dirty on
  the same file; a no-op; refused when behind; `remove` keeps the branch and record, `open`
  revives.
* `tests/test_stories.py`: Approve fast-forwards and records, refuses a branch behind, moves
  nothing when one repo is behind, finishes on retry after a partial refusal, refuses a missing
  repo, sweeps at Approve or at the last working character's turn end, Reopen revives behind its
  target, a character approves its sub-story into its own worktree.
* `tests/test_cli.py` / `tests/test_ipc.py`: the `repo` and `env` verbs; checks run per environment at an implementing handoff on the main thread and attached to the
  yield; `HANDOFF_CHECKS = "gate"` refuses on failure unless `--despite-checks`; `"attach"` posts;
  the ancestry gate before the checks; `env list` names the target.
* `tests/test_story_move.py`: key/alias; environments re-homed when the repo is registered in
  the destination, refused with an offer otherwise; sub-stories follow. *(Move is not in the
  2026-09-03 chunk.)*
* `tests/test_ui_start.py`: start screen (Scratch pinned, recents, open-folder flow) through
  `tests/ui.py`; workspace page actions.

## 10. Out of scope

Pull requests and pushes; a prune verb for canceled stories' worktrees; squashing on landing.
Shared/committed story records between team members. Execution on other machines. Repos that are
not git repositories.
