"""harness/skills.py: locating the plugin tree and reading skill bodies; the plugin tree's hygiene (Task 2)."""
import json
import re
from pathlib import Path

import pytest

from harness import skills
from harness.__main__ import ROOT


def write_skill(root: Path, name: str, body: str, description: str = "Use when testing"):
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8")


def test_default_dir_is_the_checkout_plugin(monkeypatch):
    monkeypatch.delenv("HARNESS_SKILLS_DIR", raising=False)
    assert skills.skills_dir() == ROOT / "harness" / "skills"
    assert skills.plugin_args() == ["--plugin-dir", str(ROOT / "harness" / "skills")]


def test_env_overrides_the_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))
    assert skills.skills_dir() == tmp_path and skills.plugin_args() == ["--plugin-dir", str(tmp_path)]


def test_skill_body_strips_frontmatter_and_whitespace(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))
    write_skill(tmp_path, "planning-a-story", "# Plan\n\nRead first.\n\n")
    assert skills.skill_body("planning-a-story") == "# Plan\n\nRead first."


def test_skill_body_is_empty_for_a_missing_or_blank_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))
    assert skills.skill_body("nope") == ""
    write_skill(tmp_path, "blank", "")
    assert skills.skill_body("blank") == ""


def test_phase_skill_maps_phases_to_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))
    write_skill(tmp_path, "planning-a-story", "PLAN")
    write_skill(tmp_path, "implementing-a-story", "BUILD")
    assert skills.phase_skill("planning") == "PLAN" and skills.phase_skill("implementing") == "BUILD"
    assert skills.phase_skill("done") == "" and skills.phase_skill("todo") == "" and skills.phase_skill("") == ""


def test_plugin_manifest_names_the_plugin_zharn():
    manifest = json.loads((ROOT / "harness" / "skills" / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "zharn"


# ---------------------------------------------------------------- the plugin tree (spec §5.1)

PLUGIN = ROOT / "harness" / "skills"
ZHARN = {"being-a-character", "planning-a-story", "implementing-a-story", "delegating"}
VENDORED = {"test-driven-development", "systematic-debugging", "verification-before-completion",
            "receiving-code-review", "requesting-code-review"}
FORBIDDEN = ("superpowers:", "human partner", "partner", "subagent", "Subagent", "Task tool", "TodoWrite")


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    head = text[4:text.index("\n---", 4)]
    return dict(line.split(":", 1) for line in head.splitlines() if ":" in line)


def test_the_tree_holds_exactly_the_spec_skills():
    assert {p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir()} == ZHARN | VENDORED


@pytest.mark.parametrize("name", sorted(ZHARN | VENDORED))
def test_frontmatter_is_valid_and_matches_the_directory(name):
    fm = frontmatter(PLUGIN / "skills" / name / "SKILL.md")
    assert fm["name"].strip() == name and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64
    desc = fm["description"].strip()
    assert 0 < len(desc) <= 1024 and (desc.startswith("Use when") or desc.startswith("Use always"))


@pytest.mark.parametrize("name", sorted(ZHARN | VENDORED))
def test_no_superpowers_vocabulary_survives(name):
    for path in (PLUGIN / "skills" / name).rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            hits = [w for w in FORBIDDEN if w in text]
            assert not hits, (path, hits)


def test_being_a_character_is_short():
    body = skills.skill_body("being-a-character")
    assert body and len(body.split()) < 150


def test_phase_skills_exist():
    assert skills.phase_skill("planning") and skills.phase_skill("implementing")


def test_vendored_md_lists_every_vendored_skill_and_the_license_is_present():
    text = (PLUGIN / "VENDORED.md").read_text(encoding="utf-8")
    assert "superpowers 6.3.0" in text and all(name in text for name in VENDORED)
    assert "MIT" in (ROOT / "LICENSES" / "superpowers").read_text(encoding="utf-8")


def test_systematic_debugging_leaves_the_authors_test_artifacts_upstream():
    names = {p.name for p in (PLUGIN / "skills" / "systematic-debugging").iterdir()}
    assert names == {"SKILL.md", "condition-based-waiting.md", "condition-based-waiting-example.ts",
                     "defense-in-depth.md", "root-cause-tracing.md", "find-polluter.sh"}
