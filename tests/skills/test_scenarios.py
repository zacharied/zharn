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


def test_scenarios_are_the_four_of_the_spec():
    assert runner.scenarios() == ["batch-questions", "friend-stays-in-lane", "handoff-not-silence",
                                  "outline-before-proceed"]
    for name in runner.scenarios():
        exp = runner.load(name)
        skill = exp["skill"]
        assert isinstance(skill, (str, list)) and skill
        assert exp["preset"] and exp["prompt"] and (exp["must"] or exp["must_not"])


def test_a_scenario_that_names_proceed_says_it_is_not_outline_first():
    """Start casts the protagonist position, which is outline_first, and the harness then refuses proceed
    mechanically. A scenario that requires proceed would never get it; one that forbids proceed would be
    asserting something the harness already guarantees, and would stop testing the skill. Either way the
    scenario has to open the gate itself."""
    for name in runner.scenarios():
        exp = runner.load(name)
        named = exp.get("must", []) + exp.get("must_not", [])
        if any(p["verb"] == "proceed" for p in named):
            assert exp.get("outline_first") is False, name


def test_positions_for_leaves_config_alone_by_default():
    from harness import config as cfg
    assert runner.positions_for({}) == cfg.CAST_POSITIONS
    assert runner.positions_for({}) is not cfg.CAST_POSITIONS


def test_positions_for_overrides_the_model_of_every_position():
    out = runner.positions_for({}, "claude-from-the-future")
    assert out and all(spec["model"] == "claude-from-the-future" for spec in out.values())


def test_positions_for_can_clear_the_outline_gate_for_a_run():
    out = runner.positions_for({"outline_first": False}, "")
    assert out["protagonist"]["outline_first"] is False
    assert out["protagonist"]["instructions"]      # nothing else about the position is disturbed


def test_violations_checks_must_must_not_max_and_flags():
    exp = {"must": [{"verb": "yield", "args": {"kind": "question"}}], "must_not": [{"verb": "proceed"}],
           "max": {"yield": 1}, "no_auto_yield": True, "question_has_options": True, "clean_tree": True, "committed": True}
    good = {"verbs_log": [v("yield", kind="question", questions=[{"text": "q", "options": ["a", "b"]}])], "auto_yields": 0, "dirty": "", "committed": True}
    assert runner.violations(exp, good) == []
    bad = {"verbs_log": [v("yield", kind="question", questions=[{"text": "q", "options": []}]), v("yield", kind="handoff"), v("proceed", ok=False)],
           "auto_yields": 1, "dirty": " M hello.py", "committed": False}
    out = runner.violations(exp, bad)
    assert any("forbidden" in x for x in out) and any("yield ×2 > 1" in x for x in out)
    assert any("harness yielded" in x for x in out) and any("without options" in x for x in out) and any("edited" in x for x in out)
    assert any("not committed" in x for x in out)


def test_violations_flags_work_the_lead_committed_when_its_note_said_not_to():
    """A friend shares the lead's tree; the lead is who declares the work done (spec §5.2)."""
    exp = {"uncommitted": True}
    ok = {"verbs_log": [], "auto_yields": 0, "dirty": " M docs/one.md", "committed": False}
    assert runner.violations(exp, ok) == []
    bad = runner.violations(exp, {**ok, "committed": True})
    assert bad == ["the work was committed, and the note said not to"]


def test_violations_says_so_when_the_subject_was_never_cast():
    """A friend scenario that asserts on the protagonist's log by accident would pass for the wrong reason."""
    exp = {"subject": "friend", "must": [{"verb": "yield", "args": {"kind": "handoff"}}]}
    result = {"verbs_log": [v("yield", kind="handoff")], "auto_yields": 0, "dirty": "", "committed": False}
    assert runner.violations(exp, {**result, "subject_found": True}) == []
    assert runner.violations(exp, {**result, "subject_found": False}) == [
        "no friend was ever cast, so nothing was asserted"]


def test_a_friend_scenario_forbids_a_refused_yield():
    """The ZHAR-5 symptom: a friend told the lead's playbook tries `yield --handoff` on #main and is refused,
    because only a thread's lead yields in it (spec §2.4). The refusal lands in verbs_log."""
    exp = runner.load("friend-stays-in-lane")
    assert exp["subject"] == "friend" and exp["skill"] == "being-a-friend"
    assert {"verb": "yield", "ok": False} in exp["must_not"]
    refused = {"verbs_log": [v("yield", ok=False, kind="handoff")], "auto_yields": 0, "dirty": "", "committed": False,
               "subject_found": True}
    assert any("forbidden" in x for x in runner.violations(exp, refused))


def test_violations_must_defaults_to_accepted_calls():
    exp = {"must": [{"verb": "proceed"}]}
    assert runner.violations(exp, {"verbs_log": [v("proceed", ok=False)], "auto_yields": 0, "dirty": "", "committed": False}) == ["missing {'verb': 'proceed'}"]


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
