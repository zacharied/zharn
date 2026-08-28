"""DictListModel: generic dict-row list model for QML."""
import pytest
from PySide6.QtCore import QModelIndex, Qt

from harness.qmodels import DictListModel


class Spy:
    """Counts signal emissions and keeps their args."""

    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *a: self.calls.append(a))

    def __len__(self):
        return len(self.calls)


@pytest.fixture
def model():
    m = DictListModel(["id", "name", "status"])
    m.reset([{"id": "a", "name": "A", "status": "todo"}, {"id": "b", "name": "B", "status": "done"}])
    return m


# --------------------------------------------------------------------------- read API
def test_empty_model():
    m = DictListModel(["id"])
    assert m.rowCount() == 0
    assert m.count() == 0
    assert m.rows() == []


def test_row_count_and_count_slot(model):
    assert model.rowCount() == 2
    assert model.count() == 2


def test_row_count_is_zero_for_valid_parent(model):
    assert model.rowCount(model.index(0)) == 0


def test_role_names_follow_constructor_order(model):
    names = model.roleNames()
    base = Qt.ItemDataRole.UserRole
    assert bytes(names[base]) == b"id"
    assert bytes(names[base + 1]) == b"name"
    assert bytes(names[base + 2]) == b"status"
    assert len(names) == 3


def test_data_via_index_and_role(model):
    base = Qt.ItemDataRole.UserRole
    assert model.data(model.index(0), base) == "a"
    assert model.data(model.index(1), base + 1) == "B"
    assert model.data(model.index(1), base + 2) == "done"


def test_data_unknown_role_or_invalid_index_is_none(model):
    assert model.data(model.index(0), Qt.ItemDataRole.DisplayRole) is None
    assert model.data(QModelIndex(), Qt.ItemDataRole.UserRole) is None


def test_data_missing_key_in_row_is_none():
    m = DictListModel(["id", "extra"])
    m.reset([{"id": "x"}])
    assert m.data(m.index(0), Qt.ItemDataRole.UserRole + 1) is None


def test_get_returns_copy(model):
    got = model.get(0)
    assert got == {"id": "a", "name": "A", "status": "todo"}
    got["name"] = "mutated"
    assert model.rows()[0]["name"] == "A"


@pytest.mark.parametrize("i", [-1, 2, 99])
def test_get_out_of_range_returns_empty_dict(model, i):
    assert model.get(i) == {}


# --------------------------------------------------------------------------- reset
def test_reset_replaces_rows_and_emits_count_changed(model):
    count = Spy(model.countChanged)
    about = Spy(model.modelAboutToBeReset)
    done = Spy(model.modelReset)
    model.reset([{"id": "z", "name": "Z"}])
    assert model.count() == 1
    assert model.get(0) == {"id": "z", "name": "Z"}
    assert len(count) == 1 and len(about) == 1 and len(done) == 1


def test_reset_copies_input_dicts():
    src = [{"id": "a"}]
    m = DictListModel(["id"])
    m.reset(src)
    src[0]["id"] = "changed"
    assert m.get(0)["id"] == "a"


def test_reset_to_empty(model):
    model.reset([])
    assert model.count() == 0


# --------------------------------------------------------------------------- upsert
def test_upsert_existing_updates_in_place(model):
    changed = Spy(model.dataChanged)
    inserted = Spy(model.rowsInserted)
    count = Spy(model.countChanged)
    model.upsert({"id": "a", "status": "in_progress"})
    assert model.count() == 2
    assert model.get(0) == {"id": "a", "name": "A", "status": "in_progress"}, "unmentioned keys are preserved"
    assert len(changed) == 1
    top, bottom = changed.calls[0][0], changed.calls[0][1]
    assert top.row() == 0 and bottom.row() == 0
    assert len(inserted) == 0 and len(count) == 0


def test_upsert_new_appends(model):
    changed = Spy(model.dataChanged)
    inserted = Spy(model.rowsInserted)
    count = Spy(model.countChanged)
    model.upsert({"id": "c", "name": "C"})
    assert model.count() == 3
    assert model.get(2) == {"id": "c", "name": "C"}
    assert len(inserted) == 1
    _, first, last = inserted.calls[0]
    assert (first, last) == (2, 2)
    assert len(count) == 1 and len(changed) == 0


def test_upsert_appended_row_is_a_copy(model):
    row = {"id": "c"}
    model.upsert(row)
    row["id"] = "mutated"
    assert model.get(2)["id"] == "c"


def test_upsert_with_custom_key():
    m = DictListModel(["name", "v"])
    m.reset([{"name": "x", "v": 1}, {"name": "y", "v": 2}])
    m.upsert({"name": "y", "v": 20}, key="name")
    assert m.count() == 2
    assert m.get(1) == {"name": "y", "v": 20}
    m.upsert({"name": "z", "v": 3}, key="name")
    assert m.count() == 3


def test_upsert_default_key_does_not_match_on_other_fields(model):
    model.upsert({"id": "new", "name": "A"})
    assert model.count() == 3


# --------------------------------------------------------------------------- remove
def test_remove_existing(model):
    removed = Spy(model.rowsRemoved)
    count = Spy(model.countChanged)
    model.remove("a")
    assert model.count() == 1
    assert model.get(0)["id"] == "b"
    assert len(removed) == 1
    _, first, last = removed.calls[0]
    assert (first, last) == (0, 0)
    assert len(count) == 1


def test_remove_missing_is_noop(model):
    removed = Spy(model.rowsRemoved)
    count = Spy(model.countChanged)
    model.remove("nope")
    assert model.count() == 2
    assert len(removed) == 0 and len(count) == 0


def test_remove_with_custom_key(model):
    model.remove("B", key="name")
    assert [r["id"] for r in model.rows()] == ["a"]


def test_remove_only_first_match():
    m = DictListModel(["id"])
    m.reset([{"id": "dup"}, {"id": "dup"}])
    m.remove("dup")
    assert m.count() == 1
