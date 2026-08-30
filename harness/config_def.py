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

# Appended to every agent's system prompt. {thread_id}/{task_key} are filled in.
AGENT_SYSTEM_PROMPT = (
    "You are running inside zharn as thread {thread_id} on task {task_key}. "
    "Environment variables HARNESS_THREAD_ID, HARNESS_TASK_KEY and HARNESS_CLI are set. "
    "To delegate, spawn a sibling agent on the same task and wait for it:\n"
    "  $HARNESS_CLI thread spawn --preset <name> --prompt \"...\" --wait\n"
    "List presets with `$HARNESS_CLI preset list`, threads with `$HARNESS_CLI thread list`, "
    "tasks with `$HARNESS_CLI task list`, and set task status with `$HARNESS_CLI task status <key> <status>`."
)
# When a child thread settles, send its summary to an idle parent as a new turn
NOTIFY_PARENT_ON_CHILD_SETTLED = True

# Delegation presets (bb ships none; one-click dispatch needs some)
DEFAULT_PRESETS = [
    {"name": "claude-fast", "provider": "claude-code", "model": "claude-sonnet-5", "reasoning": "medium", "permission": "auto"},
    {"name": "claude-deep", "provider": "claude-code", "model": "claude-opus-5", "reasoning": "high", "permission": "auto"},
    {"name": "claude-default", "provider": "claude-code", "model": "", "reasoning": "", "permission": "auto"},
    {"name": "codex-review", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "permission": "accept-edits"},
]
