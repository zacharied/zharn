"""Environments: where a context stands (workspace spec §4). One record per (story, repo): a managed worktree
on `zharn/<key>` cut from the parent environment's branch — the repo's `base` for a root story, `zharn/<parent>`
for a sub-story. No story works on the main checkout or in another story's tree: friends share a tree, stories
get a branch. Records live in `local/environments.json`."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

from harness import config as cfg
from harness.fsutil import write_text_atomic
from harness.procs import NoBash, run_shell


class EnvError(Exception):
    """A refused or failed environment operation; the message is what the character reads."""


def git(cwd: Path, *args: str) -> str:
    """Never prompts (a clone needing credentials must fail, not hang the GUI thread) and never runs unbounded."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo", "SSH_ASKPASS": "echo",   # git runs askpass through its
           "GIT_SSH_COMMAND": "ssh -oBatchMode=yes"}                                                    # own shell: a bare name works everywhere
    timeout = getattr(cfg, "GIT_TIMEOUT_S", 600)
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise EnvError(f"git {' '.join(args)} timed out after {timeout}s")
    if r.returncode != 0:
        raise EnvError(f"git {' '.join(args)} failed in {cwd}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def head_branch(path: Path) -> str:
    """The checked-out branch, or the short commit when detached."""
    try:
        return git(path, "symbolic-ref", "--short", "HEAD")
    except EnvError:
        return git(path, "rev-parse", "--short", "HEAD")


def _checkout_of(repo_path: Path, branch: str) -> Path | None:
    """The worktree that has `branch` checked out, or None when it is checked out nowhere."""
    wt = None
    for line in git(repo_path, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            wt = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{branch}":
            return wt
    return None


def _is_url(spec: str) -> bool:
    return "://" in spec or spec.startswith("git@")


def register_repo(ws, spec: str, name: str = "", checks: str = "", setup: str = "", base: str = "") -> dict:
    """§3.2: a path is registered as is (absolute, or relative to the workspace dir); a URL is cloned into
    <workspace>/repos/<name>/ and registered relative. `base` defaults to the HEAD branch at registration."""
    if _is_url(spec):
        name = name or spec.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        dest = ws.dir / "repos" / name
        if dest.exists():
            raise EnvError(f"{dest} exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        git(ws.dir, "clone", "-q", spec, str(dest))
        path = dest
    else:
        path = Path(spec)
        if not path.is_absolute():
            path = ws.dir / path
    path = path.resolve()
    if not (path / ".git").exists():
        raise EnvError(f"{path} is not a git repository")
    return ws.add_repo(path, name=name, checks=checks, setup=setup, base=base or head_branch(path))


def env_key(story: str, repo: str) -> str:
    return f"{story}:{repo}"


class EnvironmentStore:
    def __init__(self, workspace, parent_of: Callable[[str], str | None]):
        """`parent_of(key)` → the parent story's key, or None for a root story."""
        self.ws = workspace
        self.parent_of = parent_of
        self._file = workspace.local_dir / "environments.json"
        try:
            self._records: dict[str, dict] = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._records = {}

    def _save(self) -> None:
        write_text_atomic(self._file, json.dumps(self._records, indent=1))

    # ---------------------------------------------------------------- queries
    def get(self, story: str, repo: str) -> dict | None:
        return self._records.get(env_key(story, repo))

    def records(self, story: str) -> list[dict]:
        return [r for r in self._records.values() if r["story"] == story and not r.get("removed")]

    def _repo(self, name: str) -> tuple[dict, Path]:
        r = self.ws.repo(name)
        if r is None:
            raise EnvError(f"unknown repo {name!r}; `repo list` shows what is registered")
        p = self.ws.repo_path(r)
        if not p.is_dir():
            raise EnvError(f"repo {name!r} is missing at {p}; relocate it from the workspace page")
        return r, p

    def _base(self, repo: str) -> str:
        r, p = self._repo(repo)
        return r.get("base") or head_branch(p)

    def describe(self, rec: dict) -> dict:
        r = self.ws.repo(rec["repo"]) or {}
        try:
            target = self._resolved_target(rec)
        except EnvError:
            target = self.target(rec)   # the repo is gone: there is no HEAD to read, and the gate skips it anyway
        return {**rec, "checks": r.get("checks", ""), "target": target,
                "repo_path": str(self.ws.repo_path(r)) if r else ""}

    # ---------------------------------------------------------------- the target (§4.8)
    def target(self, rec: dict) -> str:
        """The branch this environment's branch lands in: the parent environment's branch, else the repo's `base`.
        No git call — this is read for every board row — and "" when the repo is no longer registered."""
        if rec.get("parent"):
            pk, prepo = rec["parent"].split(":", 1)
            prec = self.get(pk, prepo)
            return prec["branch"] if prec else f"zharn/{pk}"
        return (self.ws.repo(rec["repo"]) or {}).get("base", "")

    def _resolved_target(self, rec: dict) -> str:
        """The target as git must see it: a repo registered without a `base` (the workspace's own checkout) resolves
        through its HEAD branch, so no empty ref reaches git — which would read `<branch>..` as `..HEAD`."""
        return self.target(rec) or self._base(rec["repo"])

    def behind(self, rec: dict) -> int:
        """Commits on the target that the branch lacks. 0 means up to date: the target's tip is an ancestor."""
        _, repo_path = self._repo(rec["repo"])
        return int(git(repo_path, "rev-list", "--count", f"{rec['branch']}..{self._resolved_target(rec)}") or 0)

    def integrate(self, rec: dict) -> dict:
        """§4.8: fast-forward the target onto the branch's tip — in the target's worktree when it is checked out, so
        its files move too; else the ref alone. Never a merge commit: what lands is what the checks ran on."""
        _, repo_path = self._repo(rec["repo"])
        tgt, br = self._resolved_target(rec), rec["branch"]
        n_behind = self.behind(rec)
        if n_behind:
            s = "" if n_behind == 1 else "s"
            raise EnvError(f"{br} is {n_behind} commit{s} behind {tgt} in {rec['repo']} — rebase onto {tgt} (or merge it in) and retry")
        frm, to = git(repo_path, "rev-parse", "--short", tgt), git(repo_path, "rev-parse", "--short", br)
        n = int(git(repo_path, "rev-list", "--count", f"{tgt}..{br}") or 0)
        if n:
            wt = _checkout_of(repo_path, tgt)
            if wt is not None:
                git(wt, "merge", "--ff-only", "-q", br)
            else:
                git(repo_path, "branch", "-f", tgt, br)
        return {"repo": rec["repo"], "branch": br, "target": tgt, "from": frm, "to": to, "commits": n}

    def remove(self, rec: dict) -> None:
        """§4.8 cleanup: the worktree goes; the branch (the story's history) and the record stay, stamped `removed`.
        `open` brings it back on the same branch."""
        _, repo_path = self._repo(rec["repo"])
        if Path(rec["path"]).is_dir():
            git(repo_path, "worktree", "remove", "--force", rec["path"])
        else:
            git(repo_path, "worktree", "prune")
        rec["removed"] = time.time()
        self._save()

    # ---------------------------------------------------------------- open (§4.4)
    def open(self, story: str, repo: str) -> dict:
        """Idempotent per (story, repo). First use resolves the parent chain — creating the parent story's
        environment on demand — then cuts this story's worktree from the parent's branch (§4.2, §4.4)."""
        rec = self.get(story, repo)
        if rec is None:
            _, repo_path = self._repo(repo)
            parent_key = self.parent_of(story)
            parent_rec = self.open(parent_key, repo) if parent_key else None
            base = parent_rec["branch"] if parent_rec is not None else self._base(repo)
            rec = {"story": story, "repo": repo, "path": str(self.ws.local_dir / "worktrees" / repo / story),
                   "branch": f"zharn/{story}", "parent": env_key(parent_key, repo) if parent_key else None,
                   "created": time.time(), "setup_done": False}
            Path(rec["path"]).parent.mkdir(parents=True, exist_ok=True)
            git(repo_path, "worktree", "add", "-q", "-b", rec["branch"], rec["path"], base)
            self._records[env_key(story, repo)] = rec
            self._save()
        elif rec.get("removed") or not Path(rec["path"]).is_dir():
            _, repo_path = self._repo(repo)   # removed after Approve, or deleted by hand: prune, re-add on the kept branch
            git(repo_path, "worktree", "prune")
            Path(rec["path"]).parent.mkdir(parents=True, exist_ok=True)
            git(repo_path, "worktree", "add", "-q", rec["path"], rec["branch"])
            rec.pop("removed", None)
            rec["setup_done"] = False   # a fresh tree: §3.1 setup runs once in every new worktree, including a re-added one
            self._save()
        if not rec["setup_done"]:
            self._setup(rec)
        return self.describe(rec)

    def _setup(self, rec: dict) -> None:
        r, _ = self._repo(rec["repo"])
        cmd = r.get("setup", "")
        if cmd:
            timeout = getattr(cfg, "SETUP_TIMEOUT_S", 600)
            try:
                code, output = run_shell(cmd, rec["path"], timeout)
            except NoBash as e:   # the character reads this in its refused `env open`
                raise EnvError(str(e))
            if code is None:
                raise EnvError(f"setup timed out after {timeout}s in {rec['path']}")
            if code != 0:
                raise EnvError(f"setup failed in {rec['path']} (exit {code}): {output.strip()[-2000:]}")
        rec["setup_done"] = True
        self._save()
