"""Upstream defaults. On first run harness/config.py is generated as
    from harness.config_def import *
followed by your overrides. config.py is YOURS (gitignored); new upstream keys flow through.
"""

# JetBrains New UI (dark) — chrome colors, then the semantic layer the story model needs.
# Rule of thumb: phases get a soft color each; only *turns* (amber = needs you) and *liveness*
# (blue = a character mid-turn) get saturated color. Everything else is grey.
THEME = {
    # chrome
    "bg": "#1e1f22",         # editor area / window
    "panel": "#2b2d30",      # tool windows, tab bars, toolbar, status bar
    "strip": "#2b2d30",      # tool-window strips
    "border": "#393b40",
    "hover": "#393b40",
    "selection": "#2e436e",
    "selectedKey": "#b7c9f2",   # the key column (story key, section number) on a selected row
    "text": "#dfe1e5",
    "textMuted": "#868a91",
    "textDim": "#6c707a",
    "accent": "#3574f0",
    "accentHover": "#4a88ff",
    "accentSoft": "#2e436e",
    "buttonBorder": "#5a5d63",
    "tabActive": "#1e1f22",
    "tabInactive": "#2b2d30",
    "dropHint": "#3574f055",
    # semantic
    "needsYou": "#d6ae58",       # ball with you: badges, needs-you rows, the action bar's edge
    "needsYouSoft": "#d6ae5824",
    "live": "#3574f0",           # a character mid-turn
    "settled": "#5fad65",        # handoffs, done, idle-ok
    "danger": "#f75464",         # failed checks, errors, Cancel
    "dangerSoft": "#f7546420",
    "warning": "#f0a732",        # hot-reload warnings
    # phases (soft keys; canceled is grey)
    "phaseTodo": "#7fb5aa",      # backlog + todo
    "phasePlanning": "#b893ea",
    "phaseImplementing": "#7da7ff",
    "phaseDone": "#7cc47f",
    "phaseCanceled": "#868a91",
    # type: qml/fonts/ ships Inter + JetBrains Mono (OFL); the fallbacks are what the OS has
    "fontFamily": "Inter",
    "fontSize": 13,
    "fontSizeSmall": 11,
    "monoFamily": "JetBrains Mono",
    "monoSize": 12,
    # metrics (New UI defaults, 4px grid)
    "stripWidth": 40,
    "toolbarHeight": 40,
    "tabHeight": 36,
    "headerHeight": 36,
    "statusHeight": 26,
    "rowHeight": 24,
    "controlHeight": 28,
    "radius": 4,
    "radiusLarge": 6,
}

# File-watcher poll interval when inotify is unavailable (WSL drvfs, exhausted watches)
WATCH_POLL_MS = 250

# The Documents panel re-lists the registered repos' *.md files this often, while the map is on
# screen (spec docs/specs/documents-panel.md §3)
DOCS_RESCAN_MS = 2000

# ---- agents -----------------------------------------------------------------------------
# The claude-code CLI (`claude`). Override per machine with HARNESS_CLAUDE_CMD (tests use a fake).
CLAUDE_CMD = ["claude"]

# The bash that runs a repo's `checks` and `setup` (workspace spec §3.1) and that a Windows character's Claude Code
# is pinned to. "" = find it: `bash` on PATH on POSIX; on Windows CLAUDE_CODE_GIT_BASH_PATH, then Git for Windows
# beside the `git` on PATH (never System32's bash.exe, which is WSL).
BASH_PATH = ""

# harness permission → claude-code flags
PERMISSION_FLAGS = {
    "accept-edits": ["--permission-mode", "acceptEdits"],
    "auto": ["--permission-mode", "auto"],
    "full": ["--permission-mode", "bypassPermissions"],
}
# harness reasoning level → claude-code flags
EFFORT_FLAGS = {lvl: ["--effort", lvl] for lvl in ("low", "medium", "high", "xhigh", "max")}

# The skills plugin (lifecycle spec §5): passed as --plugin-dir at every spawn and read for the meta and phase
# skills. Empty = harness/skills/ in this checkout. HARNESS_SKILLS_DIR overrides at runtime.
SKILLS_DIR = ""

# System prompt for a bare context (no story). Characters get CHARACTER_SYSTEM_PROMPT instead.
BARE_CONTEXT_SYSTEM_PROMPT = (
    "You are a bare context in zharn (context {context_id}, no story): a scratch conversation. "
    "HARNESS_CLI is set; `$HARNESS_CLI context list` and `$HARNESS_CLI context show <id>` are available."
)

# System prompt for an aside (lifecycle spec §3.5): a private fork of a character, pinned to one of its comments.
ASIDE_SYSTEM_PROMPT = """You are an aside in zharn: a private copy of {name} as of its last turn, talking only with the author of story {story_key} about this comment of yours in thread #{thread_id}:

> {body}

Nobody on the story hears this conversation and none of it enters the story record. You are not a character here: you cannot post comments, yield, or call anyone, and you must not change files. If something said here should change the story, say so plainly — the author will put it in their reply on the thread."""

# First message of a forked friend (spec §3.1): no brief — it already knows — just who it is and the call note.
FORK_NOTE = ("You are {name}, a fork of {source}: a new character with a copy of its memory as of now. You cannot change "
             "{source}'s plan; if something must reach it, say `@{source}` in a comment. Your call-in note follows.\n\n")

# A recap older than this many turns of its context is stale: recast falls from rung 1 to rung 3 (spec §3.4).
RECAP_STALE_TURNS = 20

# Context usage (lifecycle spec §2.3), in tokens: the input side of a context's latest API call, read off the CLI's
# usage fields. For a 1M window; a smaller known window scales both by window/1M. Past WARN the harness asks for a
# recap once and the situation line says `recap due` until one lands; past MAX the character is asked to finish
# the step in hand and is recast at the turn boundary. Claude Code's own auto-compaction is off in every context.
CONTEXT_WARN = 300_000
CONTEXT_MAX = 500_000

# ---- environments (workspace spec §4) ---------------------------------------------------------
# What a failing repo check does at an implementing handoff (§4.6). "gate": the handoff is refused until the
# character fixes it or passes --despite-checks. "attach": it posts anyway with the red results attached.
# The trade is token burn against red handoffs.
HANDOFF_CHECKS = "gate"
CHECKS_OUTPUT_LIMIT = 4000   # characters of check output kept per repo
CHECKS_TIMEOUT_S = 1800      # per repo
GIT_TIMEOUT_S = 600          # bound on any single git subprocess (clone, worktree add/prune, …)
SETUP_TIMEOUT_S = 600        # bound on a repo's `setup` command in a fresh worktree

# Roles: what a character is cast from. `outline_first` = must get an outline approved before implementing.
DEFAULT_ROLES = [
    {"name": "protagonist", "provider": "claude-code", "model": "", "reasoning": "high", "permission": "auto", "outline_first": True,
     "instructions": "You lead this story: classify the work, ask the author what you must, outline when the work needs it, then build or delegate."},
    {"name": "claude-fast", "provider": "claude-code", "model": "claude-sonnet-5", "reasoning": "medium", "permission": "auto"},
    {"name": "claude-deep", "provider": "claude-code", "model": "claude-opus-5", "reasoning": "high", "permission": "auto"},
    {"name": "reviewer", "provider": "claude-code", "model": "claude-opus-5", "reasoning": "high", "permission": "auto",
     "instructions": "You review: read and run, change nothing. Your handoff is the review."},
    {"name": "claude-default", "provider": "claude-code", "model": "", "reasoning": "", "permission": "auto"},
    {"name": "codex-review", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "permission": "accept-edits"},
]
DEFAULT_ROLE = "protagonist"
# Role for bare contexts started from New Context (toolbar / Welcome / Contexts panel) — never the story-leading role.
DEFAULT_BARE_ROLE = "claude-default"

# System prompt for a character (lifecycle spec §5.3): stable for the life of a context. StoryStore builds it at
# every spawn from these parts, the role and the skill files — never stored. Nothing volatile belongs here: the
# situation line at the top of every message carries phase, attention, owes, awaits and environment.
CHARACTER_SYSTEM_PROMPT = """You are {name} ({character_id}), a character in zharn on story {story_key} ("{title}").
Every message you receive opens with a situation line: the phase, the thread you attend, what's owed and awaited, and where you stand. The skill for the current phase arrives in your messages whenever the phase changes; it is mandatory.

{meta_skill}

CLI (HARNESS_CLI is set; every call prints a reason and exits non-zero when refused):
  $HARNESS_CLI story yield --question [--thread t] <<'EOF'                       # ask the thread's author; only the thread's lead may
  {{"body": "preamble", "questions": [{{"text": "...", "options": ["a", "b"], "default": "a"}}, {{"text": "..."}}]}}
  EOF
  $HARNESS_CLI story yield --handoff --body "..." [--thread t]                    # hand off an outline, an answer, or finished work; on main while implementing the tree must be committed
  $HARNESS_CLI story proceed [--note "..."]                                      # planning -> implementing (main thread's lead only)
  $HARNESS_CLI story comment --body "..." [--thread t] [--to @Name]              # a note; no --thread + --to opens a thread to Name
  $HARNESS_CLI story call --role R [--as Name] [--fork] --note "..."             # a friend on its own thread; --fork copies your memory
  $HARNESS_CLI story wait                                                        # what you await, or that stopping is safe; then END YOUR TURN
  $HARNESS_CLI story resolve --thread t [--note "..."]                           # close a thread you opened that waits on you
  $HARNESS_CLI story recap --body "..." [--thread t]                             # done / in flight / gotchas / next
  $HARNESS_CLI story show · cast · inbox                                         # the record, the cast, what waits for you
  $HARNESS_CLI env open <repo>                                                  # where to work: prints the path of your story's worktree; cd there
  $HARNESS_CLI env list · repo list                                             # this story's environments; registered repos
  $HARNESS_CLI repo add <path|url> [--name N] [--checks C] [--setup S] [--base B]   # register a repo (URLs are cloned); checks run at your handoffs

{role}"""

OUTLINE_RULE_REQUIRED = ("Your role requires an outline: while planning, ask what you must, then `yield --handoff` an outline "
                         "and wait for the author to Proceed. Do not edit files while planning.")
OUTLINE_RULE_OPTIONAL = "You may `proceed` straight to implementing when the work is bounded; outline first when it is not."
