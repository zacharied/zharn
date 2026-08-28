"""Notifier: the channel UI-facing errors flow through; @intent: every QML-facing mutation reports there."""
import importlib
import sys

import pytest
from PySide6.QtCore import QObject, Slot

from harness.notify import Notifier, intent


def test_error_sets_last_error_and_emits_changed():
    n = Notifier()
    seen = []
    n.changed.connect(lambda: seen.append(n.lastError))
    n.error("boom")
    assert n.lastError == "boom"
    assert seen == ["boom"]


def test_dismiss_clears_last_error():
    n = Notifier()
    n.error("boom")
    n.dismiss()
    assert n.lastError == ""


def test_info_sets_status_without_touching_error():
    n = Notifier()
    n.error("boom")
    n.info("dispatched")
    assert n.lastError == "boom" and n.status == "dispatched"


class Store(QObject):
    def __init__(self, notifier):
        super().__init__()
        self.notifier = notifier

    @Slot(str, result=str)
    @intent
    def act(self, what):
        if what == "bad":
            raise ValueError("no good")
        return "did " + what


def test_intent_passes_return_value_through():
    assert Store(Notifier()).act("x") == "did x"


def test_intent_reports_to_notifier_then_reraises():
    n = Notifier()
    with pytest.raises(ValueError):
        Store(n).act("bad")
    assert n.lastError == "act: no good"


def test_intent_without_notifier_still_raises():
    s = Store(None)
    with pytest.raises(ValueError):
        s.act("bad")


def test_intent_body_is_hot_swappable(tmp_path, monkeypatch):
    """The reloader swaps code into the OLD function object; a decorated method must still pick up the new body."""
    from harness.shell import _patch_classes
    src = ("from PySide6.QtCore import QObject, Slot\nfrom harness.notify import intent\n"
           "class Thing(QObject):\n"
           "    notifier = None\n"
           "    @Slot(result=int)\n    @intent\n    def value(self): return {}\n")
    f = tmp_path / "intentmod.py"
    f.write_text(src.replace("{}", "1"))
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = importlib.import_module("intentmod")
    inst = mod.Thing()
    assert inst.value() == 1
    old_ns = dict(mod.__dict__)
    f.write_text(src.replace("{}", "2"))
    importlib.reload(mod)
    changed, _ = _patch_classes(old_ns, mod)
    assert not changed
    assert inst.value() == 2
    sys.modules.pop("intentmod", None)
