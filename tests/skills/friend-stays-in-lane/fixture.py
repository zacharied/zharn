"""A tiny committed repo with a docs tree the friend is asked to write into, and code it must leave alone."""
import subprocess
from pathlib import Path


def build(root: Path):
    (root / "hello.py").write_text(
        'import sys\n\n\ndef greet(name):\n    return f"hello {name}"\n\n\n'
        'if __name__ == "__main__":\n    print(greet(sys.argv[1] if len(sys.argv) > 1 else "world"))\n', encoding="utf-8")
    (root / "test_hello.py").write_text('from hello import greet\n\n\ndef test_greet():\n    assert greet("zharn") == "hello zharn"\n',
                                        encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "README.md").write_text("# fixture\n\nA greeter.\n", encoding="utf-8")
    run = lambda *a: subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@zharn", *a], cwd=root, check=True,
                                    capture_output=True)
    run("init", "-q", "-b", "main")
    run("add", "-A")
    run("commit", "-q", "-m", "fixture")
