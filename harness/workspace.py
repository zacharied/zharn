"""Workspace: a directory with a `.zharn/` — one board, one story-key prefix, a set of repos
(docs/superpowers/specs/2026-08-31-workspace-model-design.md §2, §3.1, §5.1, §6). Pure Python."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

REPO_FIELDS = ("name", "path", "checks", "setup", "base")


def default_prefix(name: str) -> str:
    letters = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:4]
    return letters or "WS"


def _toml_str(s: str) -> str:
    return json.dumps(s)


def _dump_toml(data: dict) -> str:
    """Minimal writer for our flat schema: scalars first, then `[[repos]]` tables."""
    lines = []
    for k, v in data.items():
        if k == "repos":
            continue
        lines.append(f"{k} = {_toml_str(v) if isinstance(v, str) else v}")
    for repo in data.get("repos", []):
        lines.append("")
        lines.append("[[repos]]")
        for f in REPO_FIELDS:
            lines.append(f"{f} = {_toml_str(str(repo.get(f, '')))}")
    return "\n".join(lines) + "\n"


class Workspace:
    def __init__(self, dir: Path, data: dict):
        self.dir = Path(dir).resolve()
        self.zharn_dir = self.dir / ".zharn"
        self.stories_dir = self.zharn_dir / "stories"
        self.local_dir = self.zharn_dir / "local"
        self._data = data

    # ---------------------------------------------------------------- open / create
    @staticmethod
    def exists(dir: Path) -> bool:
        return (Path(dir) / ".zharn" / "workspace.toml").is_file()

    @classmethod
    def create(cls, dir: Path, name: str | None = None, prefix: str | None = None) -> "Workspace":
        dir = Path(dir).resolve()
        if cls.exists(dir):
            raise FileExistsError(f"{dir} is already a workspace")
        folder = dir.name
        data = {"id": str(uuid.uuid4()), "name": name or folder,
                "prefix": (prefix or default_prefix(folder)).upper(), "next": 1, "repos": []}
        ws = cls(dir, data)
        ws.stories_dir.mkdir(parents=True, exist_ok=True)
        ws.local_dir.mkdir(parents=True, exist_ok=True)
        (ws.zharn_dir / ".gitignore").write_text("local/\n")
        ws.save()
        return ws

    @classmethod
    def open(cls, dir: Path) -> "Workspace":
        path = Path(dir) / ".zharn" / "workspace.toml"
        if not path.is_file():
            raise FileNotFoundError(f"{dir} has no .zharn/workspace.toml")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        data.setdefault("repos", [])
        ws = cls(dir, data)
        ws.stories_dir.mkdir(parents=True, exist_ok=True)
        ws.local_dir.mkdir(parents=True, exist_ok=True)
        return ws

    @classmethod
    def open_or_create(cls, dir: Path) -> "Workspace":
        return cls.open(dir) if cls.exists(dir) else cls.create(dir)

    def save(self) -> None:
        self.zharn_dir.mkdir(parents=True, exist_ok=True)
        (self.zharn_dir / "workspace.toml").write_text(_dump_toml(self._data), encoding="utf-8")

    # ---------------------------------------------------------------- identity
    @property
    def id(self) -> str: return self._data["id"]

    @property
    def name(self) -> str: return self._data["name"]

    @property
    def prefix(self) -> str: return self._data["prefix"]

    @property
    def next(self) -> int: return int(self._data["next"])

    @property
    def repos(self) -> list[dict]: return list(self._data["repos"])

    # ---------------------------------------------------------------- stories
    def next_key(self) -> str:
        key = f"{self.prefix}-{self.next}"
        self._data["next"] = self.next + 1
        self.save()
        return key

    def story_dir(self, key: str) -> Path:
        d = self.stories_dir / key
        d.mkdir(parents=True, exist_ok=True)
        return d

    def story_keys(self) -> list[str]:
        def num(k: str) -> int:
            try:
                return int(k.rsplit("-", 1)[1])
            except (IndexError, ValueError):
                return 0
        return sorted((p.name for p in self.stories_dir.iterdir() if p.is_dir()), key=num)

    # ---------------------------------------------------------------- repos
    def add_repo(self, path: Path, name: str = "", checks: str = "", setup: str = "", base: str = "") -> dict:
        path = Path(path).resolve()
        name = name or path.name
        if self.repo(name) is not None:
            raise ValueError(f"repo {name!r} is already registered")
        try:
            rel = path.relative_to(self.dir)
            stored = rel.as_posix() or "."
        except ValueError:
            stored = str(path)
        record = {"name": name, "path": stored, "checks": checks, "setup": setup, "base": base}
        self._data["repos"].append(record)
        self.save()
        return dict(record)

    def repo(self, name: str) -> dict | None:
        return next((dict(r) for r in self._data["repos"] if r["name"] == name), None)

    def repo_path(self, repo: dict) -> Path:
        p = Path(repo["path"])
        return p if p.is_absolute() else (self.dir / p).resolve()

    def repo_status(self, name: str) -> str:
        r = self.repo(name)
        if r is None:
            return "unknown"
        return "ok" if self.repo_path(r).is_dir() else "missing"
