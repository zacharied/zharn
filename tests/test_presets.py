"""PresetStore unit tests: config defaults, user overrides, persistence to presets.json."""
import json

import pytest

from harness import config as cfg
from harness.presets import FIELDS, PresetStore

DEFAULT_NAMES = [p["name"] for p in cfg.DEFAULT_PRESETS]


@pytest.fixture
def store(tmp_path):
    return PresetStore(tmp_path)


def read_json(tmp_path):
    return json.loads((tmp_path / "presets.json").read_text())


# --- defaults from config --------------------------------------------------

def test_defaults_come_from_config_in_order(store):
    assert store.names() == DEFAULT_NAMES


def test_every_preset_has_all_fields(store):
    for p in store.presets:
        assert set(p) == set(FIELDS), p


def test_default_presets_get_filled_in_defaults_for_missing_fields(store):
    # config entries carry no environment/instructions; the store fills them in
    p = store.get("claude-fast")
    assert p["environment"] == "project-default"
    assert p["instructions"] == ""
    # ...but explicit values from config win over the fill-ins
    assert p["provider"] == "claude-code"
    assert p["reasoning"] == "medium"
    assert p["permission"] == "auto"


def test_explicit_empty_values_in_config_are_kept(store):
    # "claude-default" deliberately leaves model/reasoning blank; that must not be "filled in"
    p = store.get("claude-default")
    assert p["model"] == ""
    assert p["reasoning"] == ""


def test_no_presets_json_on_disk_until_something_is_saved(tmp_path, store):
    store.names()
    assert not (tmp_path / "presets.json").exists()


# --- get -------------------------------------------------------------------

def test_get_is_case_insensitive(store):
    assert store.get("CLAUDE-DEEP")["name"] == "claude-deep"
    assert store.get("Claude-Deep") == store.get("claude-deep")


def test_get_unknown_returns_empty_dict(store):
    assert store.get("nope") == {}
    assert store.get("") == {}


# --- save ------------------------------------------------------------------

def test_save_adds_user_preset_to_names(store):
    store.save({"name": "mine", "provider": "claude-code", "model": "m", "reasoning": "high",
                "permission": "full", "environment": "e", "instructions": "i"})
    assert store.names() == DEFAULT_NAMES + ["mine"]
    assert store.get("mine")["instructions"] == "i"


def test_save_persists_user_preset_to_json(tmp_path, store):
    store.save({"name": "mine", "model": "m"})
    data = read_json(tmp_path)
    assert [p["name"] for p in data] == ["mine"]
    assert data[0]["model"] == "m"


def test_save_emits_presets_changed(store):
    emitted = []
    store.presetsChanged.connect(lambda: emitted.append(True))
    store.save({"name": "mine"})
    assert emitted == [True]


def test_save_keeps_only_known_fields(store):
    store.save({"name": "mine", "model": "m", "bogus": 1})
    assert "bogus" not in store.get("mine")


def test_saved_preset_with_omitted_fields_gets_store_defaults(store):
    # Same fill-in rule as config defaults: a form/caller that omits provider should not
    # produce provider == "" (which ThreadStore.spawn rejects as an unimplemented provider).
    store.save({"name": "mine", "model": "m"})
    p = store.get("mine")
    assert p["provider"] == "claude-code"
    assert p["reasoning"] == "medium"
    assert p["permission"] == "auto"
    assert p["environment"] == "project-default"


def test_save_same_name_twice_replaces_rather_than_duplicates(store):
    store.save({"name": "mine", "model": "one"})
    store.save({"name": "MINE", "model": "two"})
    assert store.names().count("mine") + store.names().count("MINE") == 1
    assert store.get("mine")["model"] == "two"


# --- user overrides a default ----------------------------------------------

def test_user_preset_overriding_default_is_a_single_entry_with_user_values(store):
    store.save({"name": "claude-fast", "provider": "claude-code", "model": "custom-model",
                "reasoning": "low", "permission": "full"})
    assert store.names().count("claude-fast") == 1
    p = store.get("claude-fast")
    assert p["model"] == "custom-model"
    assert p["reasoning"] == "low"
    assert p["permission"] == "full"


def test_user_override_keeps_the_other_defaults_in_order(store):
    store.save({"name": "claude-fast", "model": "custom-model"})
    names = store.names()
    assert sorted(names) == sorted(DEFAULT_NAMES)
    others = [n for n in DEFAULT_NAMES if n != "claude-fast"]
    assert [n for n in names if n != "claude-fast"] == others


def test_removing_the_override_restores_the_default(store):
    store.save({"name": "claude-fast", "model": "custom-model"})
    store.remove("claude-fast")
    assert store.get("claude-fast")["model"] == cfg.DEFAULT_PRESETS[0]["model"]
    assert store.names() == DEFAULT_NAMES


# --- remove ----------------------------------------------------------------

def test_remove_drops_user_preset_and_persists(tmp_path, store):
    store.save({"name": "mine", "model": "m"})
    store.remove("mine")
    assert store.get("mine") == {}
    assert store.names() == DEFAULT_NAMES
    assert read_json(tmp_path) == []


def test_remove_is_case_insensitive(store):
    store.save({"name": "mine"})
    store.remove("MINE")
    assert "mine" not in store.names()


def test_remove_unknown_name_is_a_no_op_that_keeps_defaults(store):
    store.remove("nope")
    assert store.names() == DEFAULT_NAMES


# --- persistence across instances -----------------------------------------

def test_fresh_store_over_same_dir_sees_saved_user_presets(tmp_path):
    first = PresetStore(tmp_path)
    first.save({"name": "mine", "model": "m", "provider": "claude-code"})
    first.save({"name": "claude-deep", "model": "override"})
    second = PresetStore(tmp_path)
    assert second.get("mine")["model"] == "m"
    assert second.get("claude-deep")["model"] == "override"
    assert second.names().count("claude-deep") == 1


def test_corrupt_presets_json_is_tolerated(tmp_path):
    (tmp_path / "presets.json").write_text("{not json")
    store = PresetStore(tmp_path)
    assert store.names() == DEFAULT_NAMES
    # and the store still works: saving overwrites the corrupt file
    store.save({"name": "mine"})
    assert [p["name"] for p in read_json(tmp_path)] == ["mine"]
