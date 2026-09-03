"""Real temporary git repositories for environment tests. No network, no user config needed."""
import subprocess
from pathlib import Path

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false"]


def run(cwd: Path, *args: str) -> str:
    r = subprocess.run(GIT + list(args), cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
    return r.stdout.strip()


def make_repo(path: Path, branch: str = "main") -> Path:
    """A repo at `path` with one commit on `branch` containing README.md."""
    path.mkdir(parents=True, exist_ok=True)
    run(path, "init", "-b", branch)
    (path / "README.md").write_text("hello\n")
    run(path, "add", "README.md")
    run(path, "commit", "-q", "-m", "init")
    return path


def commit_file(path: Path, name: str, text: str = "x\n") -> None:
    (path / name).write_text(text)
    run(path, "add", name)
    run(path, "commit", "-q", "-m", f"add {name}")


def branch_of(path: Path) -> str:
    return run(path, "rev-parse", "--abbrev-ref", "HEAD")
