"""The paid layer (lifecycle spec §5.4): run a scenario against real `claude -p`, with and without the skill under
test, and read verbs_log — never transcripts. The last run's baseline.json and skilled.json are committed beside
each scenario as evidence."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TURN_TIMEOUT_S = 600
RUN_TIMEOUT_S = 1800


def scenarios() -> list[str]:
    return sorted(p.name for p in HERE.iterdir() if p.is_dir() and (p / "expected.json").exists())


def load(name: str) -> dict:
    d = HERE / name
    exp = json.loads((d / "expected.json").read_text(encoding="utf-8"))
    exp["prompt"] = (d / "prompt.md").read_text(encoding="utf-8").strip()
    return exp


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def build_fixture(name: str, root: Path):
    spec = importlib.util.spec_from_file_location(f"fixture_{name.replace('-', '_')}", HERE / name / "fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.build(root)


def blanked_tree(omit: str, dest: Path) -> Path:
    """A copy of the plugin tree with skills/<omit>/SKILL.md reduced to its frontmatter: the baseline run."""
    shutil.copytree(ROOT / "harness" / "skills", dest)
    path = dest / "skills" / omit / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    end = text.index("\n---", 4) + 4
    path.write_text(text[:end] + "\n", encoding="utf-8")
    return dest


def _matches(pattern: dict, entry: dict, default_ok) -> bool:
    if entry["verb"] != pattern["verb"]:
        return False
    ok = pattern.get("ok", default_ok)
    if ok is not None and entry["ok"] != ok:
        return False
    return all(entry["args"].get(k) == val for k, val in pattern.get("args", {}).items())


def violations(expected: dict, result: dict) -> list[str]:
    log = result["verbs_log"]
    out = []
    for p in expected.get("must", []):
        if not any(_matches(p, e, True) for e in log):
            out.append(f"missing {p}")
    for p in expected.get("must_not", []):
        if any(_matches(p, e, None) for e in log):
            out.append(f"forbidden {p}")
    for verb, cap in expected.get("max", {}).items():
        n = sum(1 for e in log if e["verb"] == verb and e["ok"])
        if n > cap:
            out.append(f"{verb} ×{n} > {cap}")
    if expected.get("no_auto_yield") and result["auto_yields"]:
        out.append(f"the harness yielded for the character {result['auto_yields']} time(s)")
    if expected.get("question_has_options"):
        for e in log:
            if e["verb"] == "yield" and e["ok"] and e["args"].get("kind") == "question" and not e["args"].get("options"):
                out.append("a question yield without options")
    if expected.get("clean_tree") and result["dirty"]:
        out.append("the tree was edited: " + result["dirty"])
    return out


def _wait_for_quiet(store, key, QTest):
    """Until no context of the story is working — twice in a row, so turn-end processing (an inbox pop starts a
    new turn) has had its chance."""
    t0 = time.time()
    while time.time() - t0 < TURN_TIMEOUT_S:
        QTest.qWait(250)
        if not any(c.status in ("starting", "working") for c in store.contexts.contexts_for(key)):
            QTest.qWait(750)
            if not any(c.status in ("starting", "working") for c in store.contexts.contexts_for(key)):
                return
    raise TimeoutError(f"{key}: a turn exceeded {TURN_TIMEOUT_S}s")


def _dirty(store, key, repo: Path) -> str:
    """Edits or commits in the fixture repo or in any environment of the story."""
    base = git(repo, "rev-parse", "HEAD")
    out = []
    for path in [repo] + [Path(r["path"]) for r in store.stories.environments.records(key)]:
        if not path.is_dir():
            continue
        status = git(path, "status", "--porcelain")
        commits = git(path, "log", "--oneline", f"{base}..HEAD")
        if status or commits:
            out.append(f"{path}: {status} {commits}".strip())
    return "; ".join(out)


def run_scenario(name: str, *, omit: str | None, workdir: Path) -> dict:
    from PySide6.QtTest import QTest
    from harness.__main__ import build
    from harness.environments import register_repo

    exp = load(name)
    ws = workdir / ("baseline" if omit else "skilled")
    repo = ws / "fixture"
    repo.mkdir(parents=True)
    saved = {k: os.environ.get(k) for k in ("HARNESS_WORKSPACE", "HARNESS_SESSION", "HARNESS_CLAUDE_CMD", "HARNESS_SKILLS_DIR")}
    store = reloader = None
    try:
        build_fixture(name, repo)
        os.environ["HARNESS_WORKSPACE"] = str(ws)
        os.environ["HARNESS_SESSION"] = str(ws / "session.json")
        os.environ.pop("HARNESS_CLAUDE_CMD", None)                     # the real CLI
        if omit:
            os.environ["HARNESS_SKILLS_DIR"] = str(blanked_tree(omit, workdir / f"plugin-without-{omit}"))
        else:
            os.environ.pop("HARNESS_SKILLS_DIR", None)
        t0 = time.time()
        app, store, reloader = build(force_poll=True)
        assert reloader.load(), store.reloadError
        register_repo(store.workspace, str(repo), name="fixture", checks=exp.get("checks", ""))
        key = store.stories.create(exp["title"], exp["prompt"])
        chr_id = store.stories.start(key, exp.get("note", ""), exp["role"])
        replies = list(exp.get("replies", []))
        while time.time() - t0 < RUN_TIMEOUT_S:
            _wait_for_quiet(store, key, QTest)
            row = store.stories.get(key)
            if row["phase"] in ("done", "canceled") or row["ball"] != "author" or not replies:
                break
            store.stories.comment(key, replies.pop(0))
        comments = store.stories.comments(key)
        ch = store.stories.character(chr_id)
        return {"scenario": name, "skill_omitted": omit, "seconds": round(time.time() - t0),
                "phase": store.stories.get(key)["phase"], "ball": store.stories.get(key)["ball"],
                "verbs_log": [{k: e.get(k) for k in ("verb", "args", "ok", "error")} for e in ch["verbs_log"]],
                "comments": [{"author": c["authorName"], "kind": c["kind"], "auto_for": c.get("structured", {}).get("auto_for"),
                              "body": c["body"][:600]} for c in comments],
                "auto_yields": sum(1 for c in comments if c.get("structured", {}).get("auto_for")),
                "dirty": _dirty(store, key, repo),
                "cost_usd": round(sum(c.costUsd for c in store.contexts.contexts_for(key)), 4)}
    finally:
        if store is not None:
            store.contexts.shutdown()
        if reloader is not None:
            reloader.shutdown()
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def record(name: str, kind: str, result: dict, violations: list[str]):
    path = HERE / name / f"{kind}.json"
    path.write_text(json.dumps({"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "violations": violations, **result}, indent=1) + "\n", encoding="utf-8")
