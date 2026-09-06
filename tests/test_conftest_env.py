"""The suite must not read the HARNESS_* of whoever runs it.

An agent running these tests has its own HARNESS_CHARACTER_ID, HARNESS_STORY_KEY and friends.
They reach spawned children through the inherited environment, and CLI subprocesses the tests
build from os.environ, and the suite then reports failures that say nothing about the code.
conftest clears them at startup, keeping only the paid-scenario opt-in.
"""
import os

# The runner's identity, which nothing in the suite may ever see. Asserting the broader "no
# HARNESS_* exists" would not hold: tests/ui.py and test_agents.py set HARNESS_WORKSPACE,
# HARNESS_SESSION and HARNESS_CLAUDE_CMD as they run and never restore them. None of those is an
# identity var, and the tests that do set one (test_cli.py) use monkeypatch, so this holds
# throughout the run — which is the point. A startup-only check would pass unchanged if someone
# widened conftest's keep-list, and that edit puts the original bug straight back.
IDENTITY = ("HARNESS_CHARACTER_ID", "HARNESS_STORY_KEY", "HARNESS_CONTEXT_ID", "HARNESS_IPC",
            "HARNESS_REPO", "HARNESS_ENV", "HARNESS_ROOT", "HARNESS_CLI")


def test_no_runner_identity_var_is_live_at_any_point():
    live = [k for k in IDENTITY if k in os.environ]
    assert not live, f"the runner's identity is visible to the suite: {live}"
