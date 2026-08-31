"""fsutil: atomic text writes — a crash mid-write must never leave a half-written file (finding 4)."""
from harness.fsutil import write_text_atomic


def test_write_text_atomic_writes_the_file_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "a.json"
    write_text_atomic(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"
    assert not p.with_suffix(p.suffix + ".tmp").exists()


def test_write_text_atomic_overwrites_an_existing_file(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("old", encoding="utf-8")
    write_text_atomic(p, "new")
    assert p.read_text(encoding="utf-8") == "new"
    assert not p.with_suffix(p.suffix + ".tmp").exists()
