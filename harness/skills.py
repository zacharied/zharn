"""Skills: the files a character wakes up with (docs/specs/story-lifecycle.md §5). `harness/skills/` is one
Claude Code plugin — `--plugin-dir` at every spawn — and the harness reads the meta and phase skills out of
the same tree to inject them itself. HARNESS_SKILLS_DIR overrides the tree; the paid test runner points it
at a copy with one skill blanked."""
from __future__ import annotations

import os
from pathlib import Path

from harness import config as cfg

DEFAULT_DIR = Path(__file__).resolve().parent / "skills"
PHASE_SKILLS = {"planning": "planning-a-story", "implementing": "implementing-a-story"}


def skills_dir() -> Path:
    return Path(os.environ.get("HARNESS_SKILLS_DIR") or getattr(cfg, "SKILLS_DIR", "") or DEFAULT_DIR)


def plugin_args() -> list[str]:
    return ["--plugin-dir", str(skills_dir())]


def skill_body(name: str) -> str:
    """The markdown body of skills/<name>/SKILL.md, frontmatter stripped; "" when the file is missing or blank."""
    try:
        text = (skills_dir() / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.strip()


def phase_skill(phase: str) -> str:
    name = PHASE_SKILLS.get(phase)
    return skill_body(name) if name else ""
