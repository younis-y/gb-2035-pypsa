from pathlib import Path

import pytest

from gb2035.app.data import MARKER_FILES, find_project_root, resolve_root


def make_root(tmp_path: Path) -> Path:
    for rel in MARKER_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder\n")
    return tmp_path


def test_find_project_root_walks_up_from_a_nested_file(tmp_path: Path):
    root = make_root(tmp_path)
    nested = root / "src" / "gb2035" / "app"
    nested.mkdir(parents=True)
    assert find_project_root(nested / "main.py") == root


def test_find_project_root_accepts_the_root_itself(tmp_path: Path):
    root = make_root(tmp_path)
    assert find_project_root(root) == root


def test_find_project_root_needs_every_marker(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "scenarios.yaml").write_text("scenarios: {}\n")
    with pytest.raises(FileNotFoundError, match="no gb2035 project root"):
        find_project_root(tmp_path)


def test_resolve_root_prefers_an_explicit_flag(tmp_path: Path):
    root = make_root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert resolve_root(["--root", str(root)], elsewhere) == root


def test_resolve_root_falls_back_to_discovery(tmp_path: Path):
    root = make_root(tmp_path)
    assert resolve_root([], root / "src" / "gb2035" / "app" / "main.py") == root


def test_the_repository_is_a_project_root(repo_root: Path):
    assert find_project_root(repo_root / "src" / "gb2035" / "app") == repo_root
