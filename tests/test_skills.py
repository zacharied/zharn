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
