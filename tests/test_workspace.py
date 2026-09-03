"""Workspace: .zharn/ layout, workspace.toml, keys, repo records (workspace spec §2, §3.1, §5.1, §6)."""
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gitfix import make_repo  # noqa: E402

from harness.workspace import Workspace, default_prefix


def test_default_prefix_from_folder_name():
    assert default_prefix("zharn") == "ZHAR"
    assert default_prefix("my-project") == "MYPR"
    assert default_prefix("ab") == "AB"
    assert default_prefix("") == "WS"
    assert default_prefix("---") == "WS"


def test_create_writes_toml_with_uuid_name_prefix_and_counter(tmp_path):
    ws = Workspace.create(tmp_path / "proj")
    toml = tmp_path / "proj" / ".zharn" / "workspace.toml"
    assert toml.exists()
    uuid.UUID(ws.id)  # valid uuid
    assert ws.name == "proj" and ws.prefix == "PROJ" and ws.next == 1 and ws.repos == []
    text = toml.read_text()
    assert f'id = "{ws.id}"' in text and 'prefix = "PROJ"' in text and "next = 1" in text


def test_create_with_explicit_name_and_prefix(tmp_path):
    ws = Workspace.create(tmp_path / "x", name="Scratch", prefix="scr")
    assert ws.name == "Scratch" and ws.prefix == "SCR"


def test_create_makes_local_dir_with_gitignore(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    assert ws.local_dir == tmp_path / "p" / ".zharn" / "local"
    assert ws.local_dir.is_dir()
    assert (tmp_path / "p" / ".zharn" / ".gitignore").read_text().strip() == "local/"


def test_create_twice_raises(tmp_path):
    Workspace.create(tmp_path / "p")
    with pytest.raises(FileExistsError):
        Workspace.create(tmp_path / "p")


def test_open_reads_what_create_wrote(tmp_path):
    a = Workspace.create(tmp_path / "p", prefix="ABC")
    b = Workspace.open(tmp_path / "p")
    assert (b.id, b.name, b.prefix, b.next) == (a.id, a.name, a.prefix, a.next)


def test_open_missing_raises_and_exists_reports(tmp_path):
    assert not Workspace.exists(tmp_path / "nope")
    with pytest.raises(FileNotFoundError):
        Workspace.open(tmp_path / "nope")
    Workspace.create(tmp_path / "p")
    assert Workspace.exists(tmp_path / "p")


def test_open_or_create_is_idempotent(tmp_path):
    a = Workspace.open_or_create(tmp_path / "p")
    b = Workspace.open_or_create(tmp_path / "p")
    assert a.id == b.id


def test_next_key_increments_and_persists(tmp_path):
    ws = Workspace.create(tmp_path / "p", prefix="ZH")
    assert ws.next_key() == "ZH-1"
    assert ws.next_key() == "ZH-2"
    assert Workspace.open(tmp_path / "p").next == 3


def test_story_dir_is_created_under_stories(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    d = ws.story_dir("PROJ-1")
    assert d == tmp_path / "p" / ".zharn" / "stories" / "PROJ-1" and d.is_dir()


def test_story_keys_sorted_numerically(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    for k in ("PROJ-10", "PROJ-2", "PROJ-1"):
        ws.story_dir(k)
    assert ws.story_keys() == ["PROJ-1", "PROJ-2", "PROJ-10"]


def test_add_repo_inside_workspace_is_stored_relative(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    (tmp_path / "p" / "client").mkdir()
    r = ws.add_repo(tmp_path / "p" / "client")
    assert r == {"name": "client", "path": "client", "checks": "", "setup": "", "base": ""}
    assert ws.repo_path(r) == tmp_path / "p" / "client"
    assert Workspace.open(tmp_path / "p").repos == [r]
    assert "[[repos]]" in (tmp_path / "p" / ".zharn" / "workspace.toml").read_text()


def test_add_repo_dot_registers_the_workspace_dir_itself(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    r = ws.add_repo(tmp_path / "p")
    assert r["path"] == "." and r["name"] == "p"
    assert ws.repo_path(r) == tmp_path / "p"


def test_add_repo_outside_workspace_is_stored_absolute(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    other = tmp_path / "elsewhere"
    other.mkdir()
    r = ws.add_repo(other, name="other", checks="pytest", base="main")
    assert r["path"] == str(other.resolve()) and r["checks"] == "pytest" and r["base"] == "main"


def test_add_repo_duplicate_name_raises(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    (tmp_path / "p" / "a").mkdir()
    ws.add_repo(tmp_path / "p" / "a")
    with pytest.raises(ValueError, match="already registered"):
        ws.add_repo(tmp_path / "p" / "a")


def test_repo_lookup_and_status(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    (tmp_path / "p" / "a").mkdir()
    ws.add_repo(tmp_path / "p" / "a")
    assert ws.repo("a")["path"] == "a"
    assert ws.repo("zzz") is None
    assert ws.repo_status("a") == "ok"
    assert ws.repo_status("zzz") == "unknown"
    (tmp_path / "p" / "a").rmdir()
    assert ws.repo_status("a") == "missing"


def test_toml_roundtrip_escapes_quotes_and_backslashes(tmp_path):
    ws = Workspace.create(tmp_path / "p", name='He said "hi" C:\\x')
    assert Workspace.open(tmp_path / "p").name == 'He said "hi" C:\\x'


def test_toml_roundtrip_escapes_control_characters(tmp_path):
    ws = Workspace.create(tmp_path / "p1", name="line1\nline2")
    (tmp_path / "p1" / "repo1").mkdir()
    ws.add_repo(tmp_path / "p1" / "repo1", checks="x\ny", setup="a\tb")
    ws2 = Workspace.open(tmp_path / "p1")
    assert ws2.name == "line1\nline2"
    assert ws2.repo("repo1")["checks"] == "x\ny"
    assert ws2.repo("repo1")["setup"] == "a\tb"


# ---------------------------------------------------------------- unregister / relocate (spec §3.2, §3.3)

def test_unregister_removes_the_record_and_leaves_files(tmp_path):
    ws = Workspace.create(tmp_path / "ws")
    (tmp_path / "ws" / "client").mkdir()
    ws.add_repo(tmp_path / "ws" / "client")
    ws.unregister("client")
    assert ws.repos == [] and (tmp_path / "ws" / "client").is_dir()
    assert Workspace.open(tmp_path / "ws").repos == []
    with pytest.raises(KeyError):
        ws.unregister("client")


def test_relocate_rewrites_the_path_and_status_recovers(tmp_path):
    ws = Workspace.create(tmp_path / "ws")
    ws.add_repo(tmp_path / "elsewhere", name="lib")   # does not exist yet
    assert ws.repo_status("lib") == "missing"
    (tmp_path / "ws" / "lib").mkdir()
    rec = ws.relocate("lib", tmp_path / "ws" / "lib")
    assert rec["path"] == "lib" and ws.repo_status("lib") == "ok"
    assert Workspace.open(tmp_path / "ws").repo("lib")["path"] == "lib"


# ---------------------------------------------------------------- appdata + Scratch (spec §2.2)

def test_appdata_dir_honours_override(monkeypatch, tmp_path):
    from harness.workspace import appdata_dir
    monkeypatch.setenv("ZHARN_APPDATA", str(tmp_path / "ad"))
    assert appdata_dir() == tmp_path / "ad"
    monkeypatch.delenv("ZHARN_APPDATA")
    assert appdata_dir().name == "zharn"


def test_scratch_is_created_once_with_zharn_registered(monkeypatch, tmp_path):
    monkeypatch.setenv("ZHARN_APPDATA", str(tmp_path / "ad"))
    root = tmp_path / "zharn-src"
    root.mkdir()
    ws = Workspace.scratch(root)
    assert ws.dir == (tmp_path / "ad" / "scratch").resolve()
    assert ws.name == "Scratch" and ws.prefix == "SCR"
    assert [r["name"] for r in ws.repos] == ["zharn"] and ws.repo_path(ws.repo("zharn")) == root.resolve()
    again = Workspace.scratch(root)
    assert again.id == ws.id and [r["name"] for r in again.repos] == ["zharn"]


def test_scratch_resolves_base_at_registration_from_the_head_branch(monkeypatch, tmp_path):
    """I5: base is resolved once, at registration time — not left empty to be resolved lazily at open time."""
    monkeypatch.setenv("ZHARN_APPDATA", str(tmp_path / "ad"))
    root = make_repo(tmp_path / "zharn-src")
    ws = Workspace.scratch(root)
    assert ws.repo("zharn")["base"] == "main"


def test_scratch_base_is_empty_for_a_plain_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("ZHARN_APPDATA", str(tmp_path / "ad"))
    root = tmp_path / "zharn-src"
    root.mkdir()
    ws = Workspace.scratch(root)
    assert ws.repo("zharn")["base"] == ""


def test_scratch_is_never_special_cased():
    """§2.2: no code may test for Scratch. Only its creation (workspace.py) and the call into it may say the word."""
    import re
    from pathlib import Path
    harness = Path(__file__).resolve().parent.parent / "harness"
    for f in harness.glob("*.py"):
        if f.name in ("workspace.py", "config_def.py"):   # creation; prose in prompts ("scratch conversation")
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.search(r"scratch", line, re.I):
                assert "Workspace.scratch(" in line, f"{f.name}: {line.strip()}"
