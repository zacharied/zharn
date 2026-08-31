# Workspaces, repos, environments — design + spec (2026-08-31)

Fixes the model *around* stories: where stories live, what a repo is to zharn, where a
character stands when it works, and where all of it is stored. Complements `docs/AGENT-MODEL.md`
(which says nothing about directories) and the story lifecycle spec (`2026-08-28-story-lifecycle-design.md`).
Where code disagrees with this document, the code is wrong.

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
prefix `SCR`, and registers zharn's own source checkout as a repo in it (fork-as-config: "change
the harness" is one story away from anywhere). Scratch is pinned first on the start screen and
cannot be deleted; it is otherwise indistinguishable from any workspace and **no code may test
for it**. It is the home of everything that exists before it has a home: bare contexts started
from the start screen, one-off stories, stories about zharn itself. Stories leave Scratch by
being moved (§5.3).

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

`checks` replaces `config.CHECK_CMD` in the lifecycle spec: checks are per repo, run per
environment (§4.4).

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

### 4.1 Kinds

* **Main checkout** — the registered path itself. Where bare contexts and read-only work stand.
  Never created or destroyed by zharn.
* **Managed worktree** — created by zharn with `git worktree add` under
  `<workspace>/.zharn/local/worktrees/<repo>/<story-key>/`, on branch `zharn/<story-key>` from
  `base`. `setup` runs once after creation, in the worktree.

### 4.2 Context placement

A context runs in exactly one place: its environment's path if it has one, else the workspace
dir. A character's contexts and its minions' contexts inherit the character's environment; a
character may move between environments of *its story* between turns (`zharn env open`).

### 4.3 Lazy acquisition

A story starts with no environments. The first time a character asks for one in repo X
(`zharn env open X`), the harness creates the managed worktree for `(story, repo X)`; every
later request for the same pair returns the same worktree — one per pair, shared by the whole
cast, so a reviewer friend sees the implementor's work. The story's `repos` list is the set of
pairs that exist; it is derived, persisted for the board filter, and never edited by hand. An
author may add a repo *hint* at creation for scoping; a hint is not an environment.

Read-only investigation should use the main checkout (`zharn env open X --main`) so that stories
that only look do not sprout branches.

### 4.4 Checks

At an `implementing` handoff on the main thread the harness runs, for each of the story's
environments, that repo's `checks` in that environment, and attaches
`[{repo, cmd, exit, output}]` to the handoff comment. A repo with no `checks` contributes nothing.

### 4.5 Collisions

The same repo registered in two workspaces means both create worktrees in one `.git`. Branch
names collide only if both workspaces share a prefix *and* a story number; zharn does not defend
against this beyond reporting the git error. Choose distinct prefixes.

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
      environments.json       (story, repo) → worktree path
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

Agent processes receive `HARNESS_WORKSPACE` (dir) in addition to the existing variables.

## 7. Start screen and opening a folder

The start screen lists **Scratch** (pinned), recents, and **Open folder…**. Opening a folder:

* it has `.zharn/` → open it;
* it does not → create a workspace: name and prefix prefilled from the folder name, editable;
  if the folder is a git repo, register `.`; if it contains git repos one level down, offer them
  checked. Nothing is written until the user confirms.

Inside a workspace: a **workspace page** (repos with status and Relocate/Unregister, prefix and
name), the board, contexts, and **Move story** on every story page.

## 8. CLI

Inside a character (existing `zharn story …` verbs unchanged):

```
zharn repo add <path|url> [--name N] [--checks C] [--setup S] [--base B]   # §3.2; system comment
zharn repo list [--json]
zharn env open <repo> [--main]        # prints the environment path; creates the worktree on first use
zharn env list [--json]               # this story's environments
```

Author-only, UI (and CLI when the author is a character, for sub-stories):
`story move <key> --to <workspace-id|path>`, repo unregister, prefix rename.

## 9. Migration

> **Compatibility policy (2026-08-31, DESIGN.md §0): not built.** The checkout's `.harness/` is
> simply deleted; on first run this checkout is opened as a fresh workspace (§7) with `.`
> registered as a repo. The paragraph below documents only where each old thing's *equivalent*
> now lives.


`.harness/` in this checkout becomes `.zharn/` of a workspace whose dir is the checkout and whose
single repo is `.`. The prefix is taken from the existing store (`ABC`) so keys do not change;
`tasks.json` → `stories/<key>/` per the lifecycle spec §7; `threads/` → `local/contexts/`;
`session.json` → `local/session.json`. `config.CHECK_CMD` → the repo's `checks`.

## 10. Tests

* `tests/test_workspace.py`: create/open; relative vs absolute repo paths; folder inspection
  (repo at `.`, repos one level down); missing repo detection and relocate; prefix rename keeps
  aliases; Scratch created on first run and never special-cased (grep the source for `scratch`
  outside its creation).
* `tests/test_environments.py`: `env open` is idempotent per `(story, repo)`; branch and path
  naming; `--main` creates nothing; `setup` runs once; per-repo checks attached to a handoff.
* `tests/test_story_move.py`: key/alias; environments re-homed when the repo is registered in
  the destination, refused with an offer otherwise; sub-stories follow.
* `tests/test_ui_start.py`: start screen (Scratch pinned, recents, open-folder flow) through
  `tests/ui.py`; workspace page actions.

## 11. Out of scope

What Approve does to a story's environments (merge, PR, worktree cleanup) — its own spec, now
with a defined shape: it fans out over the story's environments. Shared/committed story records
between team members. Execution on other machines. Repos that are not git repositories.
