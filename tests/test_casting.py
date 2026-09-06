"""CastStore unit tests: the model list, the effort list, skills-only presets, and `resolve`
turning a position plus a picked model/effort/preset into the cast a context is spawned from."""
import json

import pytest

from harness import config as cfg
from harness.casting import PRESET_FIELDS, CastStore

DEFAULT_PRESET_NAMES = [p["name"] for p in cfg.DEFAULT_PRESETS]


@pytest.fixture
def store(tmp_path):
    return CastStore(tmp_path)


def read_json(tmp_path):
    return json.loads((tmp_path / "presets.json").read_text())


# ---------------------------------------------------------------- models and efforts

def test_models_come_from_config_in_order_and_carry_their_provider(store):
    assert [m["id"] for m in store.models] == [m["id"] for m in cfg.MODELS]
    assert all(m["provider"] and m["label"] for m in store.models)


def test_the_cli_default_model_is_the_empty_id(store):
    assert store.models[0]["id"] == "" and store.models[0]["provider"] == "claude-code"


def test_provider_of_looks_up_the_model_and_falls_back_for_a_typed_one(store):
    assert store.providerOf("claude-opus-5") == "claude-code"
    assert store.providerOf("gpt-5.6-sol") == "codex"
    assert store.providerOf("some-model-nobody-listed") == "claude-code"


def test_efforts_are_the_effort_flag_levels_plus_a_blank_default(store):
    assert store.efforts[0] == ""
    assert set(store.efforts[1:]) == set(cfg.EFFORT_FLAGS)


# ---------------------------------------------------------------- presets: skills, and nothing else

def test_presets_come_from_config_in_order(store):
    assert store.presetNames() == DEFAULT_PRESET_NAMES


def test_a_preset_carries_a_name_and_skills_and_nothing_else(store):
    for p in store.presets:
        assert set(p) == set(PRESET_FIELDS), p
        assert isinstance(p["skills"], list)


def test_default_preset_exists_and_exposes_the_whole_tree(store):
    assert cfg.DEFAULT_PRESET in store.presetNames()
    assert store.preset(cfg.DEFAULT_PRESET)["skills"] == ["*"]


def test_preset_skills_is_none_for_the_whole_tree_and_a_list_otherwise(store):
    assert store.preset_skills(cfg.DEFAULT_PRESET) is None
    assert "delegating" in store.preset_skills("builder")
    assert store.preset_skills("none") == []


def test_preset_skills_of_an_unknown_preset_is_none(store):
    assert store.preset_skills("nope") is None and store.preset_skills("") is None


def test_preset_lookup_is_case_insensitive_and_unknown_is_empty(store):
    assert store.preset("FULL")["name"] == "full"
    assert store.preset("nope") == {} and store.preset("") == {}


def test_no_presets_json_on_disk_until_something_is_saved(tmp_path, store):
    store.presetNames()
    assert not (tmp_path / "presets.json").exists()


def test_save_adds_a_user_preset_persists_and_emits(tmp_path, store):
    emitted = []
    store.presetsChanged.connect(lambda: emitted.append(True))
    store.save({"name": "mine", "skills": ["delegating"], "model": "sneaky"})
    assert store.presetNames() == DEFAULT_PRESET_NAMES + ["mine"]
    p = store.preset("mine")
    assert p == {"name": "mine", "skills": ["delegating"]}      # a preset controls skills and nothing else
    assert [x["name"] for x in read_json(tmp_path)] == ["mine"]
    assert emitted == [True]


def test_user_override_of_a_default_preset_is_a_single_entry_in_place(store):
    store.save({"name": "full", "skills": ["delegating"]})
    assert store.presetNames() == DEFAULT_PRESET_NAMES
    assert store.preset_skills("full") == ["delegating"]
    store.remove("FULL")
    assert store.preset_skills("full") is None


def test_fresh_store_sees_saved_presets_and_tolerates_corrupt_json(tmp_path):
    CastStore(tmp_path).save({"name": "mine", "skills": []})
    assert CastStore(tmp_path).preset("mine")["skills"] == []
    (tmp_path / "presets.json").write_text("{not json")
    assert CastStore(tmp_path).presetNames() == DEFAULT_PRESET_NAMES


# ---------------------------------------------------------------- resolve: position + picks -> cast

def test_positions_are_the_config_positions(store):
    assert set(store.positions) == set(cfg.CAST_POSITIONS)
    assert cfg.DEFAULT_POSITION in store.positions


def test_resolve_takes_instructions_permission_and_outline_rule_from_the_position(store):
    cast = store.resolve("protagonist", "claude-opus-5", "max", "builder")
    assert cast["outline_first"] is True
    assert cast["permission"] == cfg.CAST_POSITIONS["protagonist"]["permission"]
    assert cast["instructions"] == cfg.CAST_POSITIONS["protagonist"]["instructions"]
    assert cast["model"] == "claude-opus-5" and cast["effort"] == "max" and cast["preset"] == "builder"
    assert cast["position"] == "protagonist" and cast["provider"] == "claude-code"


def test_a_friend_is_not_outline_first(store):
    assert store.resolve("friend")["outline_first"] is False


def test_resolve_falls_back_to_the_positions_own_model_effort_and_preset(store):
    cast = store.resolve("friend")
    pos = cfg.CAST_POSITIONS["friend"]
    assert (cast["model"], cast["effort"], cast["preset"]) == (pos["model"], pos["effort"], pos["preset"])


def test_resolve_keeps_a_model_nobody_listed(store):
    assert store.resolve("friend", "claude-from-the-future")["model"] == "claude-from-the-future"


def test_resolve_reads_the_provider_off_the_model(store):
    assert store.resolve("friend", "gpt-5.6-sol")["provider"] == "codex"


def test_resolve_rejects_an_unknown_position_effort_or_preset(store):
    with pytest.raises(ValueError, match="position"):
        store.resolve("villain")
    with pytest.raises(ValueError, match="effort"):
        store.resolve("friend", effort="gigantic")
    with pytest.raises(ValueError, match="preset"):
        store.resolve("friend", preset="nope")


# ------------------------------------- no pick (None) against the empty pick ("", a choice config ships)

def test_an_empty_effort_is_the_providers_own_and_never_the_positions(store):
    """config.EFFORTS ships "" as a real entry: picking it means "pass no --effort", not "use the position's"."""
    assert cfg.CAST_POSITIONS["friend"]["effort"]          # the position names one, so "" cannot come from it
    assert store.resolve("friend", effort="")["effort"] == ""


def test_an_effort_nobody_picked_is_the_positions_own(store):
    assert store.resolve("friend", effort=None)["effort"] == cfg.CAST_POSITIONS["friend"]["effort"]


def test_an_empty_model_is_the_cli_default_and_never_the_positions(store, monkeypatch):
    """config.MODELS ships {"id": ""} as "cli default": picking it means "pass no --model"."""
    monkeypatch.setitem(cfg.CAST_POSITIONS["friend"], "model", "claude-opus-5")
    assert store.resolve("friend", model="")["model"] == ""
    assert store.resolve("friend", model=None)["model"] == "claude-opus-5"


def test_an_empty_preset_is_the_positions_own_because_config_ships_no_empty_preset(store):
    """Unlike models and efforts, the preset list has no empty member — there is no "no skills at all"
    below `none`. So "" and None both read as "the position's"."""
    assert store.resolve("friend", preset="")["preset"] == cfg.CAST_POSITIONS["friend"]["preset"]


# ------------------------------------- defaultsFor: what the pickers seed from

def test_defaults_for_a_position_are_its_own_three_picks(store):
    pos = cfg.CAST_POSITIONS["protagonist"]
    assert store.defaultsFor("protagonist") == {"model": pos["model"], "effort": pos["effort"],
                                                "preset": pos["preset"]}


def test_defaults_for_a_position_match_what_resolve_makes_of_no_picks(store):
    for name in cfg.CAST_POSITIONS:
        d, cast = store.defaultsFor(name), store.resolve(name)
        assert d == {k: cast[k] for k in ("model", "effort", "preset")}, name


def test_defaults_for_an_unknown_position_are_empty(store):
    assert store.defaultsFor("villain") == {}


def test_the_two_positions_the_selectors_seed_from_are_named(store):
    """QML asks for a position's defaults by name; it must not have to hardcode which name."""
    assert store.defaultPosition == cfg.DEFAULT_POSITION
    assert store.barePosition == cfg.DEFAULT_BARE_POSITION
    assert store.defaultsFor(store.defaultPosition) and store.defaultsFor(store.barePosition)


def test_resolve_of_a_cast_is_stable_for_the_same_picks(store):
    assert store.resolve("friend", "m", "high", "full") == store.resolve("friend", "m", "high", "full")


# ---------------------------------------------------------------- rebuild: a cast from what a character carries

def test_rebuild_is_resolve_when_every_pick_still_stands(store):
    assert store.rebuild("protagonist", "claude-opus-5", "max", "builder") == \
           store.resolve("protagonist", "claude-opus-5", "max", "builder")


def test_a_preset_that_no_longer_exists_costs_the_position_nothing(store):
    """W1: a preset governs skills. It must never be able to take an instruction or an outline rule with it."""
    store.save({"name": "mine", "skills": ["delegating"]})
    store.remove("mine")
    cast = store.rebuild("protagonist", effort="high", preset="mine")
    assert cast["outline_first"] is True
    assert cast["instructions"] == cfg.CAST_POSITIONS["protagonist"]["instructions"]
    assert cast["preset"] == cfg.CAST_POSITIONS["protagonist"]["preset"]


def test_an_effort_that_no_longer_exists_falls_back_to_the_positions_own(store):
    cast = store.rebuild("friend", effort="gigantic")
    assert cast["effort"] == cfg.CAST_POSITIONS["friend"]["effort"] and cast["instructions"]


def test_rebuild_keeps_an_empty_effort_because_the_providers_own_still_stands(store):
    assert store.rebuild("friend", effort="")["effort"] == ""


def test_rebuild_of_an_unknown_position_is_empty_rather_than_raising(store):
    assert store.rebuild("villain") == {}
