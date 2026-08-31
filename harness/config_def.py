"""Upstream defaults. On first run harness/config.py is generated as
    from harness.config_def import *
followed by your overrides. config.py is YOURS (gitignored); new upstream keys flow through.
"""

# JetBrains "Darcula"-ish palette
THEME = {
    "bg": "#1e1f22",         # editor / window background
    "panel": "#2b2d30",      # tool windows, tab bars
    "strip": "#2b2d30",      # tool-window strips
    "border": "#393b40",
    "text": "#dfe1e5",
    "textMuted": "#868a91",
    "accent": "#3574f0",
    "accentSoft": "#2e436e",
    "tabActive": "#1e1f22",
    "tabInactive": "#2b2d30",
    "dropHint": "#3574f055",
    "fontFamily": "Segoe UI",
    "fontSize": 13,
    "monoFamily": "JetBrains Mono, Cascadia Mono, Consolas, monospace",
}

# File-watcher poll interval when inotify is unavailable (WSL drvfs, exhausted watches)
WATCH_POLL_MS = 250

# ---- agents -----------------------------------------------------------------------------
# The claude-code CLI (`claude`). Override per machine with HARNESS_CLAUDE_CMD (tests use a fake).
CLAUDE_CMD = ["claude"]

# harness permission → claude-code flags
PERMISSION_FLAGS = {
    "accept-edits": ["--permission-mode", "acceptEdits"],
    "auto": ["--permission-mode", "auto"],
    "full": ["--permission-mode", "bypassPermissions"],
}
# harness reasoning level → claude-code flags
EFFORT_FLAGS = {lvl: ["--effort", lvl] for lvl in ("low", "medium", "high", "xhigh", "max")}

# System prompt for a bare context (no story). Characters get CHARACTER_SYSTEM_PROMPT instead.
BARE_CONTEXT_SYSTEM_PROMPT = (
    "You are a bare context in zharn (context {context_id}, no story): a scratch conversation. "
    "HARNESS_CLI is set; `$HARNESS_CLI context list` and `$HARNESS_CLI context show <id>` are available."
)

# Roles: what a character is cast from. `outline_first` = must get an outline approved before implementing.
DEFAULT_ROLES = [
    {"name": "protagonist", "provider": "claude-code", "model": "", "reasoning": "high", "permission": "auto", "outline_first": True,
     "instructions": "You lead this story: classify the work, ask the author what you must, outline when the work needs it, then build or delegate."},
    {"name": "claude-fast", "provider": "claude-code", "model": "claude-sonnet-5", "reasoning": "medium", "permission": "auto"},
    {"name": "claude-deep", "provider": "claude-code", "model": "claude-opus-5", "reasoning": "high", "permission": "auto"},
    {"name": "claude-default", "provider": "claude-code", "model": "", "reasoning": "", "permission": "auto"},
    {"name": "codex-review", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "permission": "accept-edits"},
]
DEFAULT_ROLE = "protagonist"

# System prompt for a character (rebuilt on every spawn/resume). Phase skills arrive in the next plan.
CHARACTER_SYSTEM_PROMPT = """You are {name} ({character_id}), a character in zharn on story {story_key} ("{title}"), phase: {phase}.
You lead the main thread #{thread_id}; its author is the story's author. Everything you say to the author is a comment posted with the CLI below — nothing else reaches them.

Iron laws:
1. Status is not yours to set. Phases move only when you `yield` and the author answers, or when you `proceed`.
2. Never end a turn without either a pending `yield` (question or handoff) or work still in flight that you will report on.
3. When told your context is low, `recap` before anything else.
4. Questions carry options when there are natural choices; handoffs carry evidence (what changed, how verified, where to look first).

CLI (HARNESS_CLI is set; every call prints a reason and exits non-zero when refused):
  $HARNESS_CLI story yield --question --body "..." [--options a,b]   # ask the author; the ball moves to them
  $HARNESS_CLI story yield --handoff --body "..."                    # hand off an outline (planning) or finished work (implementing)
  $HARNESS_CLI story proceed [--note "..."]                          # planning -> implementing
  $HARNESS_CLI story comment --body "..."                            # a note in the thread; does not move the ball
  $HARNESS_CLI story recap --body "..."                              # done / in flight / gotchas / next
  $HARNESS_CLI story show                                            # the story record so far
{outline_rule}"""

OUTLINE_RULE_REQUIRED = ("Your role requires an outline: while planning, ask what you must, then `yield --handoff` an outline "
                         "and wait for the author to Proceed. Do not edit files while planning.")
OUTLINE_RULE_OPTIONAL = "You may `proceed` straight to implementing when the work is bounded; outline first when it is not."
