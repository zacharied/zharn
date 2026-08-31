"""Layout tree: the single source of truth for docks, strips and Main Content Containers.

Pure data (JSON-friendly dicts) + intents. No Qt here. QML renders the tree and sends
intents back; QML never owns layout state, so the QML tree is disposable (hot reload).

Node shapes:
  split: {"type":"split","id","orientation":"horizontal"|"vertical","children":[node...],"ratios":[float...]}
  tabs:  {"type":"tabs","id","tabs":[{"kind","key","title"}...],"active":int}
  docks: {side: {"panels":[kind...],"active":kind|None,"mode":"docked"|"strip"|"overlay","size":int}}
"""
from __future__ import annotations

import copy
import itertools
import json

SIDES = ("left", "right", "bottom")
EDGE_ORIENTATION = {"left": "horizontal", "right": "horizontal", "top": "vertical", "bottom": "vertical"}

_ids = itertools.count(1)


def new_id(prefix: str) -> str:
    return f"{prefix}{next(_ids)}"


def tab(kind: str, key: str | None = None, title: str | None = None) -> dict:
    return {"kind": kind, "key": key or kind, "title": title or kind}


def tabs(items=None, active: int = 0) -> dict:
    return {"type": "tabs", "id": new_id("g"), "tabs": list(items or []), "active": active}


def split(orientation: str, children: list, ratios=None) -> dict:
    n = len(children)
    return {"type": "split", "id": new_id("s"), "orientation": orientation,
            "children": children, "ratios": list(ratios) if ratios else [1.0 / n] * n}


def default_layout() -> dict:
    return {
        "center": tabs([tab("welcome", "welcome", "Welcome")]),
        "docks": {
            "left": {"panels": ["board", "files"], "active": "board", "mode": "docked", "size": 280},
            "right": {"panels": ["contexts"], "active": "contexts", "mode": "docked", "size": 320},
            "bottom": {"panels": ["terminal", "git"], "active": "terminal", "mode": "strip", "size": 220},
        },
        "activeGroup": None,
    }


def _normalize(ratios):
    s = sum(ratios) or 1.0
    return [r / s for r in ratios]


class Layout:
    def __init__(self, data: dict | None = None):
        self.data = data or default_layout()
        # make sure ids never collide with a restored session
        for node, _ in self.iter_nodes():
            num = "".join(ch for ch in node["id"] if ch.isdigit())
            if num:
                while next(_ids) < int(num):
                    pass

    # ---------------------------------------------------------------- serialization
    def to_json(self) -> str:
        return json.dumps(self.data)

    @classmethod
    def from_json(cls, text: str) -> "Layout":
        return cls(json.loads(text))

    def copy(self) -> "Layout":
        return Layout(copy.deepcopy(self.data))

    # ---------------------------------------------------------------- queries
    def iter_nodes(self, node=None, parent=None):
        node = self.data["center"] if node is None else node
        yield node, parent
        if node["type"] == "split":
            for child in node["children"]:
                yield from self.iter_nodes(child, node)

    def find(self, node_id: str):
        for node, parent in self.iter_nodes():
            if node["id"] == node_id:
                return node, parent
        raise KeyError(node_id)

    def groups(self) -> list:
        return [n for n, _ in self.iter_nodes() if n["type"] == "tabs"]

    def active_group(self) -> dict:
        gid = self.data.get("activeGroup")
        for g in self.groups():
            if g["id"] == gid:
                return g
        g = self.groups()[0]
        self.data["activeGroup"] = g["id"]
        return g

    def find_tab(self, kind: str, key: str):
        for g in self.groups():
            for i, t in enumerate(g["tabs"]):
                if t["kind"] == kind and t["key"] == key:
                    return g, i
        return None, None

    # ---------------------------------------------------------------- intents
    def open(self, kind: str, key: str | None = None, title: str | None = None, group_id: str | None = None) -> str:
        """Open content; if already open anywhere, just focus it. Returns the group id."""
        key = key or kind
        g, i = self.find_tab(kind, key)
        if g is not None:
            g["active"] = i
            self.data["activeGroup"] = g["id"]
            return g["id"]
        g = self.find(group_id)[0] if group_id else self.active_group()
        g["tabs"].append(tab(kind, key, title))
        g["active"] = len(g["tabs"]) - 1
        self.data["activeGroup"] = g["id"]
        return g["id"]

    def activate(self, group_id: str, index: int):
        g = self.find(group_id)[0]
        if 0 <= index < len(g["tabs"]):
            g["active"] = index
        self.data["activeGroup"] = group_id

    def close(self, group_id: str, index: int):
        g = self.find(group_id)[0]
        if not (0 <= index < len(g["tabs"])):
            return
        g["tabs"].pop(index)
        g["active"] = min(g["active"], len(g["tabs"]) - 1) if g["tabs"] else 0
        self._collapse_if_empty(group_id)

    def split_group(self, group_id: str, orientation: str, new_tab: dict | None = None, before: bool = False) -> str:
        """Split a group; the new (sibling) group holds `new_tab` (or is empty). Returns new group id."""
        node, parent = self.find(group_id)
        new_group = tabs([new_tab] if new_tab else [])
        if parent is not None and parent["orientation"] == orientation:
            idx = parent["children"].index(node)
            at = idx if before else idx + 1
            parent["children"].insert(at, new_group)
            n = len(parent["children"])
            share = parent["ratios"][idx] / 2
            parent["ratios"][idx] = share
            parent["ratios"].insert(at, share)
            parent["ratios"] = _normalize(parent["ratios"])
        else:
            pair = [new_group, node] if before else [node, new_group]
            new_split = split(orientation, pair)
            self._replace(node, new_split, parent)
        self.data["activeGroup"] = new_group["id"]
        return new_group["id"]

    def move(self, from_group: str, index: int, to_group: str, to_index: int | None = None):
        src = self.find(from_group)[0]
        if not (0 <= index < len(src["tabs"])):
            return
        if from_group == to_group:
            t = src["tabs"].pop(index)
            to_index = len(src["tabs"]) if to_index is None else max(0, min(to_index, len(src["tabs"])))
            src["tabs"].insert(to_index, t)
            src["active"] = to_index
            return
        t = src["tabs"].pop(index)
        src["active"] = min(src["active"], len(src["tabs"]) - 1) if src["tabs"] else 0
        dst = self.find(to_group)[0]
        to_index = len(dst["tabs"]) if to_index is None else max(0, min(to_index, len(dst["tabs"])))
        dst["tabs"].insert(to_index, t)
        dst["active"] = to_index
        self.data["activeGroup"] = to_group
        self._collapse_if_empty(from_group)

    def move_to_edge(self, from_group: str, index: int, target_group: str, edge: str):
        """Drop a tab on the left/right/top/bottom edge of another group → split it."""
        src = self.find(from_group)[0]
        if not (0 <= index < len(src["tabs"])):
            return
        if from_group == target_group and len(src["tabs"]) == 1:
            return  # splitting a lone tab away from itself is a no-op
        t = src["tabs"].pop(index)
        src["active"] = min(src["active"], len(src["tabs"]) - 1) if src["tabs"] else 0
        self.split_group(target_group, EDGE_ORIENTATION[edge], new_tab=t, before=edge in ("left", "top"))
        self._collapse_if_empty(from_group)

    def set_ratios(self, split_id: str, ratios):
        node = self.find(split_id)[0]
        if node["type"] == "split" and len(ratios) == len(node["children"]):
            node["ratios"] = _normalize([max(0.02, float(r)) for r in ratios])

    def toggle_panel(self, side: str, panel: str):
        d = self.data["docks"][side]
        if d["active"] == panel and d["mode"] == "docked":
            d["mode"] = "strip"
        else:
            d["active"] = panel
            d["mode"] = "docked"

    def show_panel(self, panel: str):
        """Make a panel visible wherever it lives (docked + active), unlike toggle_panel."""
        for side in SIDES:
            d = self.data["docks"][side]
            if panel in d["panels"]:
                d["active"], d["mode"] = panel, "docked"
                return side
        raise KeyError(panel)

    def set_dock_mode(self, side: str, mode: str):
        self.data["docks"][side]["mode"] = mode

    def set_dock_size(self, side: str, size: int):
        self.data["docks"][side]["size"] = max(120, int(size))

    def move_panel(self, panel: str, to_side: str):
        for side in SIDES:
            d = self.data["docks"][side]
            if panel in d["panels"]:
                d["panels"].remove(panel)
                if d["active"] == panel:
                    d["active"] = d["panels"][0] if d["panels"] else None
                    if d["active"] is None:
                        d["mode"] = "strip"
        dst = self.data["docks"][to_side]
        dst["panels"].append(panel)
        dst["active"] = panel
        dst["mode"] = "docked"

    # ---------------------------------------------------------------- internals
    def _replace(self, old, new, parent):
        if parent is None:
            self.data["center"] = new
        else:
            parent["children"][parent["children"].index(old)] = new

    def _collapse_if_empty(self, group_id: str):
        node, parent = self.find(group_id)
        if node["tabs"] or parent is None:
            if not node["tabs"] and parent is None:
                self.data["activeGroup"] = node["id"]
            return
        idx = parent["children"].index(node)
        parent["children"].pop(idx)
        parent["ratios"].pop(idx)
        parent["ratios"] = _normalize(parent["ratios"])
        if len(parent["children"]) == 1:
            _, grand = self.find(parent["id"])
            self._replace(parent, parent["children"][0], grand)
        if self.data.get("activeGroup") == group_id:
            self.data["activeGroup"] = self.groups()[0]["id"]
