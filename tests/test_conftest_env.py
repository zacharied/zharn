"""The suite must not inherit the HARNESS_* of whoever runs it.

An agent running these tests has its own HARNESS_CHARACTER_ID, HARNESS_STORY_KEY and friends.
They reach spawned children through the inherited environment, and CLI subprocesses the tests
build from os.environ, and the suite then reports failures that say nothing about the code.
conftest clears them at startup, keeping only the paid-scenario opt-in.
"""


def test_the_ambient_harness_environment_is_cleared(ambient_harness_at_startup):
    # Not "no HARNESS_* exists now": tests set their own as they run. This is the startup snapshot.
    assert not ambient_harness_at_startup, \
        f"conftest left the runner's own harness vars in place: {ambient_harness_at_startup}"
