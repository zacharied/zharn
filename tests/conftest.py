import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")


def _scrub_ambient_harness_env():
    # An agent running the suite carries its own HARNESS_* (character, story, IPC). They reach
    # spawned children through the inherited environment, and CLI subprocesses the tests build from
    # os.environ, and the suite then fails on who ran it rather than on the code. Keep only the
    # paid-scenario opt-in, which is read from the ambient environment by design (README, "Skills").
    keep = {"HARNESS_PAID_TESTS", "HARNESS_PAID_MODEL"}
    for k in [k for k in os.environ if k.upper().startswith("HARNESS_") and k.upper() not in keep]:
        del os.environ[k]


_scrub_ambient_harness_env()
os.environ["HARNESS_SESSION"] = str(ROOT / "tests" / "_out" / "session.json")
(ROOT / "tests" / "_out").mkdir(exist_ok=True)

# One QGuiApplication for the whole session: QML needs a *Gui* app, and a plain QCoreApplication
# created by an earlier test module would make every later engine.load() abort.
from PySide6.QtGui import QGuiApplication  # noqa: E402
_app = QGuiApplication.instance() or QGuiApplication(sys.argv)
