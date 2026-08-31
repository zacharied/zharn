"""RoleStore unit tests: config defaults, user overrides, persistence to roles.json, outline_first."""
import json

import pytest

from harness import config as cfg
from harness.roles import FIELDS, RoleStore

DEFAULT_NAMES = [r["name"] for r in cfg.DEFAULT_ROLES]


@pytest.fixture
def store(tmp_path):
    return RoleStore(tmp_path)


def read_json(tmp_path):
    return json.loads((tmp_path / "roles.json").read_text())


def test_defaults_come_from_config_in_order(store):
    assert store.names() == DEFAULT_NAMES


def test_every_role_has_all_fields(store):
    for r in store.roles:
        assert set(r) == set(FIELDS), r


def test_default_role_exists_and_is_outline_first(store):
    assert cfg.DEFAULT_ROLE in store.names()
    assert store.get(cfg.DEFAULT_ROLE)["outline_first"] is True


def test_fill_ins_for_missing_fields(store):
    r = store.get("claude-fast")
    assert r["environment"] == "project-default" and r["instructions"] == "" and r["outline_first"] is False
    assert r["provider"] == "claude-code" and r["reasoning"] == "medium" and r["permission"] == "auto"


def test_explicit_empty_values_in_config_are_kept(store):
    r = store.get("claude-default")
    assert r["model"] == "" and r["reasoning"] == ""


def test_no_roles_json_on_disk_until_something_is_saved(tmp_path, store):
    store.names()
    assert not (tmp_path / "roles.json").exists()


def test_get_is_case_insensitive_and_unknown_is_empty(store):
    assert store.get("CLAUDE-DEEP")["name"] == "claude-deep"
    assert store.get("nope") == {} and store.get("") == {}


def test_save_adds_user_role_persists_and_emits(tmp_path, store):
    emitted = []
    store.rolesChanged.connect(lambda: emitted.append(True))
    store.save({"name": "mine", "model": "m", "outline_first": True, "bogus": 1})
    assert store.names() == DEFAULT_NAMES + ["mine"]
    r = store.get("mine")
    assert r["outline_first"] is True and "bogus" not in r and r["provider"] == "claude-code"
    assert [x["name"] for x in read_json(tmp_path)] == ["mine"]
    assert emitted == [True]


def test_save_same_name_twice_replaces(store):
    store.save({"name": "mine", "model": "one"})
    store.save({"name": "MINE", "model": "two"})
    assert store.names().count("mine") + store.names().count("MINE") == 1
    assert store.get("mine")["model"] == "two"


def test_user_override_of_a_default_is_single_entry_in_place(store):
    store.save({"name": "claude-fast", "model": "custom"})
    assert store.names() == DEFAULT_NAMES
    assert store.get("claude-fast")["model"] == "custom"
    store.remove("claude-fast")
    assert store.get("claude-fast")["model"] == cfg.DEFAULT_ROLES[1]["model"]


def test_remove_drops_user_role_and_is_case_insensitive(tmp_path, store):
    store.save({"name": "mine"})
    store.remove("MINE")
    assert store.get("mine") == {} and read_json(tmp_path) == []
    store.remove("nope")
    assert store.names() == DEFAULT_NAMES


def test_fresh_store_sees_saved_roles_and_tolerates_corrupt_json(tmp_path):
    RoleStore(tmp_path).save({"name": "mine", "model": "m"})
    assert RoleStore(tmp_path).get("mine")["model"] == "m"
    (tmp_path / "roles.json").write_text("{not json")
    s = RoleStore(tmp_path)
    assert s.names() == DEFAULT_NAMES
    s.save({"name": "mine"})
    assert [r["name"] for r in read_json(tmp_path)] == ["mine"]
