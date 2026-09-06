"""harness/skills.py: locating the plugin tree and reading skill bodies; the plugin tree's hygiene (Task 2)."""
import json
import os
import re
import shutil
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


def test_skill_name_keys_on_position_then_phase():
    assert skills.skill_name("protagonist", "planning") == "planning-a-story"
    assert skills.skill_name("protagonist", "implementing") == "implementing-a-story"
    assert skills.skill_name("friend", "planning") == "being-a-friend"
    assert skills.skill_name("friend", "implementing") == "being-a-friend"


def test_skill_name_is_empty_where_no_skill_belongs():
    assert skills.skill_name("bare", "planning") == ""        # a bare context is on no story
    assert skills.skill_name("bare", "implementing") == ""
    assert skills.skill_name("protagonist", "done") == ""     # terminal and pre-start phases carry none
    assert skills.skill_name("protagonist", "todo") == ""
    assert skills.skill_name("protagonist", "") == ""
    assert skills.skill_name("", "implementing") == "implementing-a-story"   # no position: the phase decides


def test_skill_for_reads_the_body_of_whatever_skill_name_picked(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))
    write_skill(tmp_path, "implementing-a-story", "BUILD")
    write_skill(tmp_path, "being-a-friend", "ONE PIECE")
    assert skills.skill_for("protagonist", "implementing") == "BUILD"
    assert skills.skill_for("friend", "implementing") == "ONE PIECE"
    assert skills.skill_for("friend", "done") == ""
    assert skills.skill_for("bare", "implementing") == ""


def test_plugin_manifest_names_the_plugin_zharn():
    manifest = json.loads((ROOT / "harness" / "skills" / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "zharn"


# ---------------------------------------------------------------- the plugin tree (spec §5.1)

PLUGIN = ROOT / "harness" / "skills"
ZHARN = {"being-a-character", "being-a-friend", "planning-a-story", "implementing-a-story", "delegating"}
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


def test_every_injected_skill_exists_in_the_tree():
    for name in ("being-a-character", "being-a-friend", "planning-a-story", "implementing-a-story"):
        assert skills.skill_body(name)


def test_vendored_md_lists_every_vendored_skill_and_the_license_is_present():
    text = (PLUGIN / "VENDORED.md").read_text(encoding="utf-8")
    assert "superpowers 6.3.0" in text and all(name in text for name in VENDORED)
    assert "MIT" in (ROOT / "LICENSES" / "superpowers").read_text(encoding="utf-8")


def test_systematic_debugging_leaves_the_authors_test_artifacts_upstream():
    names = {p.name for p in (PLUGIN / "skills" / "systematic-debugging").iterdir()}
    assert names == {"SKILL.md", "condition-based-waiting.md", "condition-based-waiting-example.ts",
                     "defense-in-depth.md", "root-cause-tracing.md", "find-polluter.sh"}


@pytest.mark.parametrize("name", ["being-a-character", "being-a-friend", "planning-a-story", "implementing-a-story"])
def test_injected_skills_avoid_the_fake_claudes_trigger_words(name):
    """tests/fake_claude.py fails a turn on "fail" and sleeps on "slow"; these bodies ride every brief and delivery."""
    body = skills.skill_body(name).lower()
    assert "fail" not in body and "slow" not in body


# ---------------------------------------------------------------- preset-filtered plugin trees (§5.1)

@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A source tree of three skills, with the plugin manifest the real one has."""
    src = tmp_path / "src"
    (src / ".claude-plugin").mkdir(parents=True)
    (src / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "zharn", "version": "0.0.1"}))
    for name in ("being-a-character", "delegating", "test-driven-development"):
        write_skill(src, name, f"body of {name}")
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(src))
    return src


def names_in(d: Path) -> set[str]:
    return {p.name for p in (d / "skills").iterdir() if p.is_dir()}


def test_no_names_hands_over_the_whole_source_tree(tree, tmp_path):
    assert skills.plugin_dir(names=None, cache=tmp_path / "cache") == tree
    assert skills.plugin_args(names=None, cache=tmp_path / "cache") == ["--plugin-dir", str(tree)]


def test_names_without_a_cache_fall_back_to_the_whole_tree(tree):
    assert skills.plugin_dir("builder", ["delegating"], None) == tree


def test_a_preset_gets_a_filtered_copy_named_after_it(tree, tmp_path):
    cache = tmp_path / "cache"
    d = skills.plugin_dir("builder", ["delegating"], cache)
    assert d == cache / "builder" and names_in(d) == {"delegating"}
    assert (d / "skills" / "delegating" / "SKILL.md").read_text(encoding="utf-8").endswith("body of delegating\n")
    assert json.loads((d / ".claude-plugin" / "plugin.json").read_text())["name"] == "zharn"


def test_an_empty_preset_gets_a_tree_with_no_skills(tree, tmp_path):
    d = skills.plugin_dir("none", [], tmp_path / "cache")
    assert names_in(d) == set() and (d / ".claude-plugin" / "plugin.json").exists()


def test_a_named_skill_that_does_not_exist_is_skipped(tree, tmp_path):
    d = skills.plugin_dir("odd", ["delegating", "no-such-skill"], tmp_path / "cache")
    assert names_in(d) == {"delegating"}


def test_the_filtered_tree_is_rebuilt_when_the_preset_changes(tree, tmp_path):
    cache = tmp_path / "cache"
    skills.plugin_dir("p", ["delegating"], cache)
    assert names_in(skills.plugin_dir("p", ["being-a-character"], cache)) == {"being-a-character"}


def test_the_filtered_tree_is_rebuilt_when_the_source_skill_changes(tree, tmp_path):
    cache = tmp_path / "cache"
    d = skills.plugin_dir("p", ["delegating"], cache)
    (tree / "skills" / "delegating" / "SKILL.md").write_text(
        "---\nname: delegating\ndescription: Use when testing\n---\n\nrewritten\n", encoding="utf-8")
    d = skills.plugin_dir("p", ["delegating"], cache)
    assert "rewritten" in (d / "skills" / "delegating" / "SKILL.md").read_text(encoding="utf-8")


def test_an_unchanged_tree_is_reused_rather_than_rebuilt(tree, tmp_path):
    cache = tmp_path / "cache"
    d = skills.plugin_dir("p", ["delegating"], cache)
    marker = d / "skills" / "delegating" / "untouched.txt"
    marker.write_text("still here")
    skills.plugin_dir("p", ["delegating"], cache)
    assert marker.exists()


def test_plugin_args_points_at_the_filtered_tree(tree, tmp_path):
    cache = tmp_path / "cache"
    assert skills.plugin_args("builder", ["delegating"], cache) == ["--plugin-dir", str(cache / "builder")]


def test_a_different_source_tree_is_not_served_from_another_ones_cache(tree, tmp_path, monkeypatch):
    """A3: the stamp records mtime+size, which a copy preserves — the source path has to be in it too."""
    cache = tmp_path / "cache"
    skills.plugin_dir("p", ["delegating"], cache)
    other = tmp_path / "other"
    shutil.copytree(tree, other)
    src_file = tree / "skills" / "delegating" / "SKILL.md"
    copy = other / "skills" / "delegating" / "SKILL.md"
    body = src_file.read_text(encoding="utf-8")
    copy.write_text(body[:-11] + "OTHERTREE!\n", encoding="utf-8")   # same length, other bytes
    assert copy.stat().st_size == src_file.stat().st_size
    st = src_file.stat()
    os.utime(copy, ns=(st.st_atime_ns, st.st_mtime_ns))                            # and the same mtime
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(other))
    d = skills.plugin_dir("p", ["delegating"], cache)
    assert "OTHERTREE!" in (d / "skills" / "delegating" / "SKILL.md").read_text(encoding="utf-8")


def test_editing_the_plugin_manifest_rebuilds_the_filtered_tree(tree, tmp_path):
    cache = tmp_path / "cache"
    skills.plugin_dir("p", ["delegating"], cache)
    (tree / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "zharn", "version": "9.9.9"}))
    d = skills.plugin_dir("p", ["delegating"], cache)
    assert json.loads((d / ".claude-plugin" / "plugin.json").read_text())["version"] == "9.9.9"


def test_a_rebuild_survives_a_directory_that_could_not_be_removed(tree, tmp_path, monkeypatch):
    """A2: rmtree is best-effort on Windows, where a live child can hold a SKILL.md open."""
    cache = tmp_path / "cache"
    skills.plugin_dir("p", ["delegating"], cache)
    monkeypatch.setattr(skills.shutil, "rmtree", lambda *a, **k: None)     # nothing gets removed
    d = skills.plugin_dir("p", ["being-a-character"], cache)               # must not raise FileExistsError
    assert (d / "skills" / "being-a-character" / "SKILL.md").exists()
    assert json.loads((d / ".zharn-stamp.json").read_text())["names"] == ["being-a-character"]
