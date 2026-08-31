"""Workspace: .zharn/ layout, workspace.toml, keys, repo records (workspace spec §2, §3.1, §5.1, §6)."""
import uuid

import pytest

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
