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
    l.toggle_panel("left", "tasks")   # active+docked → strip
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
