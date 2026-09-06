import os, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
# An agent running the suite carries its own HARNESS_* (character, story, IPC). They reach spawned
# children through the inherited environment and CLI subprocesses the tests build from os.environ,
# and the suite then fails on who ran it rather than on the code. Keep only the paid-scenario
# opt-in, which is read from the ambient environment by design (README, "Skills").
_KEEP = {"HARNESS_PAID_TESTS", "HARNESS_PAID_MODEL"}
for _k in [k for k in os.environ if k.upper().startswith("HARNESS_") and k.upper() not in _KEEP]:
    del os.environ[_k]
# Tests set their own HARNESS_* as they run (tests/ui.py, test_agents.py), so "no HARNESS_* exists"
# is not an invariant anyone can assert later. What is assertable is this snapshot: what the runner
# brought in and we failed to remove. test_conftest_env.py reads it through the fixture below.
AMBIENT_HARNESS_AT_STARTUP = sorted(k for k in os.environ if k.upper().startswith("HARNESS_") and k.upper() not in _KEEP)

os.environ["HARNESS_SESSION"] = str(ROOT / "tests" / "_out" / "session.json")
(ROOT / "tests" / "_out").mkdir(exist_ok=True)

# One QGuiApplication for the whole session: QML needs a *Gui* app, and a plain QCoreApplication
# created by an earlier test module would make every later engine.load() abort.
from PySide6.QtGui import QGuiApplication  # noqa: E402
_app = QGuiApplication.instance() or QGuiApplication(sys.argv)


@pytest.fixture
def ambient_harness_at_startup():
    """The runner's own HARNESS_* that survived conftest's scrub — empty on a healthy run."""
    return AMBIENT_HARNESS_AT_STARTUP
