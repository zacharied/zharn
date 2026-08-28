import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ["HARNESS_SESSION"] = str(ROOT / "tests" / "_out" / "session.json")
(ROOT / "tests" / "_out").mkdir(exist_ok=True)
