import subprocess
from pathlib import Path

from gb2035.cli import _git_sha


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_git_sha_marks_uncommitted_tracked_changes_dirty(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "model.py").write_text("a = 1\n")
    _git(tmp_path, "add", "model.py")
    _git(tmp_path, "commit", "-q", "-m", "init")
    clean = _git_sha(tmp_path)
    assert clean and not clean.endswith("-dirty")
    (tmp_path / "results.csv").write_text("new untracked output\n")
    assert _git_sha(tmp_path) == clean, "untracked outputs are not code changes"
    (tmp_path / "model.py").write_text("a = 2\n")
    assert _git_sha(tmp_path) == f"{clean}-dirty"
