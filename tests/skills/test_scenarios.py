"""Spec §5.4, the paid layer: scenarios against real `claude -p`, with and without the skill under test; assertions
read verbs_log. The cheap tests here exercise the runner's logic; the paid ones need HARNESS_PAID_TESTS=1."""
import json
import os
from pathlib import Path

import pytest

from tests.skills import runner

paid = pytest.mark.skipif(not os.environ.get("HARNESS_PAID_TESTS"), reason="real claude -p; set HARNESS_PAID_TESTS=1")


def v(verb, ok=True, **args):
    return {"verb": verb, "args": args, "ok": ok, "error": ""}


def test_scenarios_are_the_three_of_the_spec():
    assert runner.scenarios() == ["batch-questions", "handoff-not-silence", "outline-before-proceed"]
    for name in runner.scenarios():
        exp = runner.load(name)
        skill = exp["skill"]
        assert isinstance(skill, (str, list)) and skill
        assert exp["role"] and exp["prompt"] and (exp["must"] or exp["must_not"])


def test_violations_checks_must_must_not_max_and_flags():
    exp = {"must": [{"verb": "yield", "args": {"kind": "question"}}], "must_not": [{"verb": "proceed"}],
           "max": {"yield": 1}, "no_auto_yield": True, "question_has_options": True, "clean_tree": True}
    good = {"verbs_log": [v("yield", kind="question", options=["a", "b"])], "auto_yields": 0, "dirty": ""}
    assert runner.violations(exp, good) == []
    bad = {"verbs_log": [v("yield", kind="question", options=[]), v("yield", kind="handoff"), v("proceed", ok=False)],
           "auto_yields": 1, "dirty": " M hello.py"}
    out = runner.violations(exp, bad)
    assert any("forbidden" in x for x in out) and any("yield ×2 > 1" in x for x in out)
    assert any("harness yielded" in x for x in out) and any("without options" in x for x in out) and any("edited" in x for x in out)


def test_violations_must_defaults_to_accepted_calls():
    exp = {"must": [{"verb": "proceed"}]}
    assert runner.violations(exp, {"verbs_log": [v("proceed", ok=False)], "auto_yields": 0, "dirty": ""}) == ["missing {'verb': 'proceed'}"]


def test_blanked_tree_keeps_frontmatter_and_drops_the_body(tmp_path):
    dest = runner.blanked_tree("planning-a-story", tmp_path / "plug")
    text = (dest / "skills" / "planning-a-story" / "SKILL.md").read_text()
    assert text.startswith("---\nname: planning-a-story\n") and text.rstrip().endswith("---")
    assert "Iron Law" in (dest / "skills" / "implementing-a-story" / "SKILL.md").read_text()
    assert (dest / ".claude-plugin" / "plugin.json").exists()


def test_blanked_tree_blanks_a_list_of_skills(tmp_path):
    dest = runner.blanked_tree(["being-a-character", "planning-a-story"], tmp_path / "plug")
    for name in ("being-a-character", "planning-a-story"):
        text = (dest / "skills" / name / "SKILL.md").read_text()
        assert text.startswith(f"---\nname: {name}\n") and text.rstrip().endswith("---")
    assert "Iron Law" in (dest / "skills" / "implementing-a-story" / "SKILL.md").read_text()


def test_fixtures_build_a_committed_git_repo(tmp_path):
    for name in runner.scenarios():
        root = tmp_path / name
        root.mkdir()
        runner.build_fixture(name, root)
        assert (root / ".git").is_dir() and (root / "hello.py").exists()
        assert runner.git(root, "status", "--porcelain") == "" and runner.git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_run_scenario_restores_env_and_shuts_down_nothing_when_the_app_never_builds(monkeypatch, tmp_path):
    monkeypatch.delenv("HARNESS_WORKSPACE", raising=False)
    monkeypatch.setenv("HARNESS_SESSION", "sentinel")
    monkeypatch.setattr(runner, "build_fixture", lambda name, root: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        runner.run_scenario("batch-questions", omit=None, workdir=tmp_path)
    assert os.environ["HARNESS_SESSION"] == "sentinel"
    assert "HARNESS_WORKSPACE" not in os.environ


def test_run_scenario_refuses_to_spend_without_the_paid_flag(monkeypatch, tmp_path):
    monkeypatch.delenv("HARNESS_WORKSPACE", raising=False)
    monkeypatch.delenv("HARNESS_PAID_TESTS", raising=False)
    monkeypatch.setattr(runner, "build_fixture", lambda name, root: None)
    with pytest.raises(AssertionError, match="HARNESS_PAID_TESTS"):
        runner.run_scenario("batch-questions", omit=None, workdir=tmp_path)
    assert "HARNESS_WORKSPACE" not in os.environ


@paid
@pytest.mark.parametrize("name", runner.scenarios())
def test_scenario_with_and_without_the_skill(name, tmp_path):
    exp = runner.load(name)
    model = os.environ.get("HARNESS_PAID_MODEL", "")    # empty: the CLI's default model
    baseline = runner.run_scenario(name, omit=exp["skill"], workdir=tmp_path, model=model)
    runner.record(name, "baseline", baseline, runner.violations(exp, baseline))
    skilled = runner.run_scenario(name, omit=None, workdir=tmp_path, model=model)
    bad = runner.violations(exp, skilled)
    runner.record(name, "skilled", skilled, bad)
    assert not bad, bad
