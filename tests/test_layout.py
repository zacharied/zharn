from harness.layout import Layout, tab


def ids(layout):
    return [g["id"] for g in layout.groups()]


def test_default_has_one_group_with_welcome():
    l = Layout()
    assert len(l.groups()) == 1
    assert l.groups()[0]["tabs"][0]["kind"] == "welcome"


def test_open_focuses_existing_tab_instead_of_duplicating():
    l = Layout()
    g = l.open("thread", "t1", "T1")
    l.open("thread", "t2", "T2")
    assert l.open("thread", "t1") == g
    assert [t["key"] for t in l.groups()[0]["tabs"]] == ["welcome", "t1", "t2"]
    assert l.groups()[0]["active"] == 1


def test_split_then_close_collapses_back():
    l = Layout()
    g0 = ids(l)[0]
    g1 = l.split_group(g0, "horizontal", tab("thread", "t1", "T1"))
    assert l.data["center"]["type"] == "split" and len(ids(l)) == 2
    assert l.data["activeGroup"] == g1
    l.close(g1, 0)
    assert l.data["center"]["type"] == "tabs" and ids(l) == [g0]


def test_split_same_orientation_flattens():
    l = Layout()
    g0 = ids(l)[0]
    g1 = l.split_group(g0, "horizontal", tab("a"))
    g2 = l.split_group(g1, "horizontal", tab("b"))
    root = l.data["center"]
    assert [c["id"] for c in root["children"]] == [g0, g1, g2]
    assert abs(sum(root["ratios"]) - 1) < 1e-9


def test_move_to_edge_splits_and_cleans_source():
    l = Layout()
    g0 = ids(l)[0]
    l.open("thread", "t1", "T1")
    l.move_to_edge(g0, 1, g0, "right")
    root = l.data["center"]
    assert root["type"] == "split" and root["orientation"] == "horizontal"
    assert root["children"][0]["id"] == g0 and root["children"][1]["tabs"][0]["key"] == "t1"
    l.move_to_edge(g0, 0, root["children"][1]["id"], "top")
    # g0 emptied → removed; remaining: vertical split inside
    assert g0 not in ids(l)
    assert l.data["center"]["type"] == "split" and l.data["center"]["orientation"] == "vertical"


def test_move_between_groups_and_reorder():
    l = Layout()
    g0 = ids(l)[0]
    l.open("a", "1"); l.open("b", "2")
    g1 = l.split_group(g0, "vertical")
    l.move(g0, 2, g1, None)
    assert [t["kind"] for t in l.find(g1)[0]["tabs"]] == ["b"]
    l.move(g0, 0, g0, 1)
    assert [t["kind"] for t in l.find(g0)[0]["tabs"]] == ["a", "welcome"]


def test_lone_tab_to_own_edge_is_noop():
    l = Layout()
    g0 = ids(l)[0]
    l.move_to_edge(g0, 0, g0, "left")
    assert l.data["center"]["type"] == "tabs"


def test_toggle_panel_and_docks():
    l = Layout()
    l.toggle_panel("left", "board")   # active+docked → strip
    assert l.data["docks"]["left"]["mode"] == "strip"
    l.toggle_panel("left", "files")
    assert l.data["docks"]["left"] == {**l.data["docks"]["left"], "active": "files", "mode": "docked"}
    l.move_panel("files", "bottom")
    assert "files" not in l.data["docks"]["left"]["panels"]
    assert l.data["docks"]["bottom"]["active"] == "files"
    l.set_dock_size("left", 10)
    assert l.data["docks"]["left"]["size"] == 120


def test_json_roundtrip_and_id_uniqueness():
    l = Layout()
    g0 = ids(l)[0]
    l.split_group(g0, "horizontal", tab("a"))
    l2 = Layout.from_json(l.to_json())
    assert l2.data == l.data
    new = l2.split_group(ids(l2)[0], "vertical", tab("b"))
    assert len(set(ids(l2))) == 3 and new not in ids(l)


# ---------------------------------------------------------------- edge cases


def test_close_out_of_range_index_is_noop():
    l = Layout()
    before = l.copy().data
    l.close(ids(l)[0], 5)
    l.close(ids(l)[0], -1)
    assert l.data == before


def test_close_last_tab_in_root_leaves_empty_root_group():
    l = Layout()
    g0 = ids(l)[0]
    l.close(g0, 0)
    root = l.data["center"]
    assert root["type"] == "tabs" and root["id"] == g0
    assert root["tabs"] == [] and root["active"] == 0
    assert l.data["activeGroup"] == g0


def test_activate_bad_index_sets_group_but_not_active():
    l = Layout()
    g0 = ids(l)[0]
    l.open("a", "1")
    l.data["activeGroup"] = None
    l.activate(g0, 9)
    assert l.data["activeGroup"] == g0
    assert l.find(g0)[0]["active"] == 1


def test_set_ratios_wrong_length_is_ignored():
    l = Layout()
    l.split_group(ids(l)[0], "horizontal", tab("a"))
    root = l.data["center"]
    before = list(root["ratios"])
    l.set_ratios(root["id"], [0.2, 0.3, 0.5])
    assert root["ratios"] == before


def test_set_ratios_clamps_tiny_values_then_normalizes():
    l = Layout()
    l.split_group(ids(l)[0], "horizontal", tab("a"))
    root = l.data["center"]
    l.set_ratios(root["id"], [0.0, 1.0])
    assert abs(sum(root["ratios"]) - 1) < 1e-9
    assert abs(root["ratios"][0] - 0.02 / 1.02) < 1e-9
    assert root["ratios"][0] > 0


def test_set_dock_size_floors_at_120():
    l = Layout()
    l.set_dock_size("right", 0)
    assert l.data["docks"]["right"]["size"] == 120
    l.set_dock_size("right", 500)
    assert l.data["docks"]["right"]["size"] == 500


def test_toggle_panel_on_strip_dock_docks_it_and_sets_active():
    l = Layout()
    bottom = l.data["docks"]["bottom"]
    assert bottom["mode"] == "strip"
    l.toggle_panel("bottom", "git")
    assert bottom["mode"] == "docked" and bottom["active"] == "git"


def test_toggle_panel_other_panel_switches_active_keeps_docked():
    l = Layout()
    left = l.data["docks"]["left"]
    l.toggle_panel("left", "files")
    assert left["active"] == "files" and left["mode"] == "docked"


def test_move_panel_only_panel_leaves_side_empty_strip():
    l = Layout()
    l.move_panel("contexts", "left")
    right = l.data["docks"]["right"]
    assert right["panels"] == [] and right["active"] is None and right["mode"] == "strip"
    assert l.data["docks"]["left"]["panels"][-1] == "contexts"


def test_move_panel_to_same_side_keeps_single_entry():
    l = Layout()
    l.move_panel("files", "left")
    left = l.data["docks"]["left"]
    assert left["panels"].count("files") == 1
    assert left["active"] == "files" and left["mode"] == "docked"


def test_active_group_falls_back_and_repairs_stale_id():
    l = Layout()
    l.data["activeGroup"] = "g999"
    g = l.active_group()
    assert g is l.groups()[0]
    assert l.data["activeGroup"] == g["id"]


def test_restored_layout_never_reuses_high_ids():
    l = Layout({"center": {"type": "split", "id": "s500", "orientation": "horizontal",
                           "children": [{"type": "tabs", "id": "g400", "tabs": [tab("a")], "active": 0},
                                        {"type": "tabs", "id": "g501", "tabs": [tab("b")], "active": 0}],
                           "ratios": [0.5, 0.5]},
                "docks": Layout().data["docks"], "activeGroup": "g400"})
    for _ in range(5):
        l.split_group(l.active_group()["id"], "vertical", tab("x"))
    all_ids = [n["id"] for n, _ in l.iter_nodes()]
    assert len(all_ids) == len(set(all_ids))
    assert all(int(i[1:]) > 501 for i in all_ids if i not in ("s500", "g400", "g501"))


def test_find_unknown_id_raises_keyerror():
    import pytest
    with pytest.raises(KeyError):
        Layout().find("nope")


def test_open_with_explicit_group_id_appends_there():
    l = Layout()
    g0 = ids(l)[0]
    g1 = l.split_group(g0, "horizontal")
    l.data["activeGroup"] = g0
    assert l.open("thread", "t1", "T1", group_id=g1) == g1
    assert [t["key"] for t in l.find(g1)[0]["tabs"]] == ["t1"]
    assert [t["key"] for t in l.find(g0)[0]["tabs"]] == ["welcome"]
    assert l.data["activeGroup"] == g1


def test_split_group_before_puts_new_group_first():
    l = Layout()
    g0 = ids(l)[0]
    g1 = l.split_group(g0, "horizontal", tab("a"), before=True)
    assert [c["id"] for c in l.data["center"]["children"]] == [g1, g0]
    g2 = l.split_group(g0, "horizontal", tab("b"), before=True)
    assert [c["id"] for c in l.data["center"]["children"]] == [g1, g2, g0]


def test_move_to_index_beyond_end_clamps():
    l = Layout()
    g0 = ids(l)[0]
    l.open("a", "1"); l.open("b", "2")
    l.move(g0, 0, g0, 99)
    assert [t["kind"] for t in l.find(g0)[0]["tabs"]] == ["a", "b", "welcome"]
    g1 = l.split_group(g0, "vertical", tab("c"))
    l.move(g0, 0, g1, 99)
    assert [t["kind"] for t in l.find(g1)[0]["tabs"]] == ["c", "a"]
    assert l.find(g1)[0]["active"] == 1


def test_move_to_own_edge_from_multi_tab_group_splits_in_two():
    l = Layout()
    g0 = ids(l)[0]
    l.open("a", "1")
    l.move_to_edge(g0, 0, g0, "bottom")
    root = l.data["center"]
    assert root["type"] == "split" and root["orientation"] == "vertical"
    assert len(root["children"]) == 2 and root["children"][0]["id"] == g0
    assert [t["kind"] for t in root["children"][0]["tabs"]] == ["a"]
    assert [t["kind"] for t in root["children"][1]["tabs"]] == ["welcome"]


def test_show_panel_docks_it_wherever_it_lives_and_keeps_it_shown():
    l = Layout()
    l.toggle_panel("bottom", "git")
    l.toggle_panel("bottom", "git")  # collapsed again
    assert l.show_panel("git") == "bottom"
    assert l.data["docks"]["bottom"] == {**l.data["docks"]["bottom"], "active": "git", "mode": "docked"}
    assert l.show_panel("git") == "bottom"  # idempotent, not a toggle
    assert l.data["docks"]["bottom"]["mode"] == "docked"
    import pytest
    with pytest.raises(KeyError):
        l.show_panel("nope")
