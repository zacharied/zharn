"""Skills: the files a character wakes up with (docs/specs/story-lifecycle.md §5). `harness/skills/` is one
Claude Code plugin — `--plugin-dir` at every spawn — and the harness reads the injected skills out of
the same tree to deliver them itself. HARNESS_SKILLS_DIR overrides the tree; the paid test runner points it
at a copy with one skill blanked."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from harness import config as cfg

DEFAULT_DIR = Path(__file__).resolve().parent / "skills"
PHASE_SKILLS = {"planning": "planning-a-story", "implementing": "implementing-a-story"}
# A position that leads no story of its own takes one skill in every phase (spec §5.3).
POSITION_SKILLS = {"friend": "being-a-friend"}
# Not on a story at all: the phase skills are inert there, so it takes none (spec §5.1).
NO_SKILL_POSITIONS = {"bare"}
META_SKILL = "being-a-character"


def always_on() -> set[str]:
    """The skills the harness injects itself (spec §5.3). Every built tree carries them whatever a preset
    names: `being-a-character` tells a character its skill is mandatory and to re-read it with the Skill
    tool, and a skill missing from the plugin cannot be re-read."""
    return {META_SKILL, *PHASE_SKILLS.values(), *POSITION_SKILLS.values()}


def skills_dir() -> Path:
    return Path(os.environ.get("HARNESS_SKILLS_DIR") or getattr(cfg, "SKILLS_DIR", "") or DEFAULT_DIR)


def _stamp(src: Path, names: list[str]) -> dict:
    """What a filtered tree was built from: the skills asked for, and the mtime/size of every file
    under each of them. A change to any of it rebuilds."""
    files = {}
    for root in [src / ".claude-plugin"] + [src / "skills" / name for name in names]:
        for f in sorted(root.rglob("*")):
            if f.is_file():
                st = f.stat()
                files[f.relative_to(src).as_posix()] = [int(st.st_mtime_ns), st.st_size]
    return {"source": str(src), "names": list(names), "files": files}


def plugin_dir(preset: str = "", names: list[str] | None = None, cache: Path | None = None) -> Path:
    """The plugin tree a spawn is handed. `names` is the preset's skill list (spec §5.1); None — the whole
    tree, which is also what a caller with nowhere to build gets. Otherwise a filtered copy under
    `cache/<preset>`, rebuilt whenever the preset or any source file under it changes."""
    src = skills_dir()
    if names is None or cache is None:
        return src
    # Before the stamp, so the cache key covers them and editing one rebuilds the tree.
    names = sorted(set(names) | always_on())
    out = Path(cache) / (preset or "preset")
    stamp, marker = _stamp(src, names), out / ".zharn-stamp.json"
    try:
        if json.loads(marker.read_text(encoding="utf-8")) == stamp:
            return out
    except (OSError, ValueError):
        pass
    marker.unlink(missing_ok=True)            # a rebuild that dies partway must not look finished
    shutil.rmtree(out, ignore_errors=True)    # best effort: on Windows a live child may hold a SKILL.md open
    shutil.rmtree(out / "skills", ignore_errors=True)
    (out / "skills").mkdir(parents=True, exist_ok=True)
    manifest = src / ".claude-plugin"
    if manifest.is_dir():
        shutil.copytree(manifest, out / ".claude-plugin", dirs_exist_ok=True)
    for name in names:
        if (src / "skills" / name).is_dir():
            shutil.copytree(src / "skills" / name, out / "skills" / name, dirs_exist_ok=True)
    marker.write_text(json.dumps(stamp), encoding="utf-8")
    return out


def plugin_args(preset: str = "", names: list[str] | None = None, cache: Path | None = None) -> list[str]:
    return ["--plugin-dir", str(plugin_dir(preset, names, cache))]


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


def skill_name(position: str, phase: str) -> str:
    """The skill directory a character in `position` wakes up with while the story is in `phase`; "" for a
    position or a phase that carries none (spec §5.3).

    Only the phases in PHASE_SKILLS carry a skill at all, positions included: a friend on a story that is
    done or canceled is owed nothing, exactly as its protagonist is. The position tables are then
    membership tests, not `.get(...) or ...` fallbacks — neither None nor "" would stop a bare context
    falling through to the phase table and picking up the protagonist's skill."""
    if phase not in PHASE_SKILLS:
        return ""
    if position in POSITION_SKILLS:
        return POSITION_SKILLS[position]
    if position in NO_SKILL_POSITIONS:
        return ""
    return PHASE_SKILLS[phase]


def skill_for(position: str, phase: str) -> str:
    name = skill_name(position, phase)
    return skill_body(name) if name else ""
