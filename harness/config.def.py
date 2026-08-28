"""Upstream defaults. On first run this file is copied to harness/config.py — that copy is
YOURS (gitignored): edit it, or edit anything else; your fork is your config.
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

# Delegation presets (bb ships none; one-click dispatch needs some)
DEFAULT_PRESETS = [
    {"name": "claude-fast", "provider": "claude-code", "model": "claude-sonnet-5", "reasoning": "medium", "permission": "auto"},
    {"name": "claude-deep", "provider": "claude-code", "model": "claude-fable-5", "reasoning": "high", "permission": "auto"},
    {"name": "codex-review", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "permission": "accept-edits"},
]
