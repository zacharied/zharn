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


def blanked_tree(omit: str | list[str], dest: Path) -> Path:
    """A copy of the plugin tree with skills/<name>/SKILL.md reduced to its frontmatter for each name in omit
    (one name or a list): the baseline run."""
    shutil.copytree(ROOT / "harness" / "skills", dest)
    for name in [omit] if isinstance(omit, str) else omit:
        path = dest / "skills" / name / "SKILL.md"
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
            if e["verb"] == "yield" and e["ok"] and e["args"].get("kind") == "question" \
                    and not any(q.get("options") for q in (e["args"].get("questions") or [])):
                out.append("a question yield without options")
    if expected.get("clean_tree") and result["dirty"]:
        out.append("the tree was edited: " + result["dirty"])
    if expected.get("committed") and not result["committed"]:
        out.append("the work was not committed: " + (result["dirty"] or "no environment"))
    if expected.get("uncommitted") and result["committed"]:
        out.append("the work was committed, and the note said not to")
    if expected.get("subject") and not result.get("subject_found", True):
        out.append(f"no {expected['subject']} was ever cast, so nothing was asserted")
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


def _committed(store, key, repo: Path) -> bool:
    """Every environment of the story is clean and at least one commit past the fixture's HEAD (the tree gate, §4.6)."""
    base = git(repo, "rev-parse", "HEAD")
    envs = [Path(r["path"]) for r in store.stories.environments.records(key)]
    return bool(envs) and all(p.is_dir() and not git(p, "status", "--porcelain") and git(p, "log", "--oneline", f"{base}..HEAD")
                              for p in envs)


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


def positions_for(exp: dict, model: str = "") -> dict:
    """The CAST_POSITIONS one run uses. `model` overrides the model of every position — friends the character
    casts included. A scenario that has to reach implementing without an outline sets `"outline_first": false`
    and gets it cleared; Start casts the protagonist position, which is outline-first by default, so a scenario
    whose `must` names proceed would otherwise be refused the verb."""
    from harness import config as cfg
    out = {}
    for position, spec in cfg.CAST_POSITIONS.items():
        spec = dict(spec)
        if model:
            spec["model"] = model
        if "outline_first" in exp:
            spec["outline_first"] = bool(exp["outline_first"])
        out[position] = spec
    return out


def run_scenario(name: str, *, omit: str | list[str] | None, workdir: Path, model: str = "") -> dict:
    """One run. `model` and the scenario's own outline gate are applied for this run only, by rewriting the
    in-memory CAST_POSITIONS (see `positions_for`); nothing on disk changes."""
    from PySide6.QtTest import QTest
    from harness import config as cfg
    from harness.__main__ import build
    from harness.environments import register_repo

    exp = load(name)
    names = ([omit] if isinstance(omit, str) else omit) if omit else []
    ws = workdir / ("baseline" if names else "skilled")
    repo = ws / "fixture"
    repo.mkdir(parents=True)
    saved = {k: os.environ.get(k) for k in ("HARNESS_WORKSPACE", "HARNESS_SESSION", "HARNESS_CLAUDE_CMD", "HARNESS_SKILLS_DIR")}
    store = reloader = None
    saved_positions = cfg.CAST_POSITIONS
    try:
        build_fixture(name, repo)
        os.environ["HARNESS_WORKSPACE"] = str(ws)
        os.environ["HARNESS_SESSION"] = str(ws / "session.json")
        assert os.environ.get("HARNESS_PAID_TESTS"), "run_scenario spends money: set HARNESS_PAID_TESTS=1"
        os.environ.pop("HARNESS_CLAUDE_CMD", None)                     # the real CLI
        if names:
            os.environ["HARNESS_SKILLS_DIR"] = str(blanked_tree(names, workdir / f"plugin-without-{'+'.join(names)}"))
        else:
            os.environ.pop("HARNESS_SKILLS_DIR", None)
        t0 = time.time()
        app, store, reloader = build(force_poll=True)
        assert reloader.load(), store.reloadError
        cfg.CAST_POSITIONS = positions_for(exp, model)      # this run only — restored in the finally below
        register_repo(store.stories.workspace, str(repo), name="fixture", checks=exp.get("checks", ""))
        key = store.stories.create(exp["title"], exp["prompt"])
        chr_id = store.stories.start(key, exp.get("note", ""), exp.get("model", ""), exp.get("effort", ""),
                                     exp.get("preset", ""))
        replies = list(exp.get("replies", []))
        while time.time() - t0 < RUN_TIMEOUT_S:
            _wait_for_quiet(store, key, QTest)
            row = store.stories.get(key)
            if row["phase"] in ("done", "canceled") or row["ball"] != "author" or not replies:
                break
            store.stories.comment(key, replies.pop(0))
        comments = store.stories.comments(key)
        # Whose verbs the scenario is about. Default the protagonist; `"subject": "friend"` asserts on the
        # friend the protagonist called instead, which is the only way to reach a non-protagonist position —
        # the harness casts a friend from a `call`, never from Start (spec §2.2).
        subject, found = store.stories.character(chr_id), True
        if exp.get("subject") and exp["subject"] != "protagonist":
            match = [c for c in store.stories.cast(key) if c["position"] == exp["subject"]]
            found = bool(match)
            subject = match[0] if match else subject
        ch = subject
        return {"scenario": name, "skill_omitted": names, "seconds": round(time.time() - t0),
                "subject": ch["name"], "subject_position": ch["position"], "subject_found": found,
                "model": sorted({c.model for c in store.contexts.contexts_for(key) if c.model}),
                "phase": store.stories.get(key)["phase"], "ball": store.stories.get(key)["ball"],
                "verbs_log": [{k: e.get(k) for k in ("verb", "args", "ok", "error")} for e in ch["verbs_log"]],
                "comments": [{"author": c["authorName"], "kind": c["kind"], "auto_for": c.get("structured", {}).get("auto_for"),
                              "body": c["body"][:600]} for c in comments],
                "auto_yields": sum(1 for c in comments if c.get("structured", {}).get("auto_for")),
                "dirty": _dirty(store, key, repo),
                "committed": _committed(store, key, repo),
                "cost_usd": round(sum(c.costUsd for c in store.contexts.contexts_for(key)), 4)}
    finally:
        cfg.CAST_POSITIONS = saved_positions
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
