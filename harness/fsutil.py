"""Filesystem helpers shared across stores: atomic text writes so a crash or hot-reload mid-write
never leaves a half-written `story.json` / `index.json` / `workspace.toml` behind."""
from __future__ import annotations

import os
from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` atomically: write to a sibling `.tmp` file, then `os.replace` it
    over `path`. On POSIX and Windows `os.replace` is atomic, so readers never see a partial file."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
