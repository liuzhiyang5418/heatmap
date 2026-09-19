"""文件发现层（``githotmap.scanner.walker``）的单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from githotmap.scanner.walker import (
    DEFAULT_EXCLUDES,
    find_repository_root,
    is_excluded,
    walk_candidates,
)


def _make_tree(root: Path, files: dict[str, str]) -> None:
    """按 ``{相对路径: 内容}`` 建目录树。"""
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------- #
# 排除规则
# --------------------------------------------------------------------------- #
def test_is_excluded_matches_directory_segment() -> None:
    patterns = ["__pycache__/"]
    assert is_excluded("a/b/__pycache__/c.py", patterns) is True
    assert is_excluded("a/b/c.py", patterns) is False


def test_is_excluded_directory_segment_supports_globs() -> None:
    """``*.egg-info/`` 必须命中 ``src/githotmap.egg-info/PKG-INFO``。"""
    assert is_excluded("src/githotmap.egg-info/PKG-INFO", ["*.egg-info/"]) is True


def test_is_excluded_path_glob() -> None:
    patterns = ["tests/*"]
    assert is_excluded("tests/test_a.py", patterns) is True
    assert is_excluded("src/test_a.py", patterns) is False


def test_is_excluded_ignores_blank_patterns() -> None:
    assert is_excluded("a.py", ["", "   "]) is False


def test_is_excluded_without_patterns() -> None:
    assert is_excluded("a.py", []) is False


# --------------------------------------------------------------------------- #
# Git 根定位
# --------------------------------------------------------------------------- #
def test_find_repository_root_walks_up(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "pkg" / "sub"
    nested.mkdir(parents=True)
    assert find_repository_root(nested) == tmp_path.resolve()


def test_find_repository_root_prefers_nearest_and_accepts_git_file(
    tmp_path: Path,
) -> None:
    """git worktree / submodule 的 ``.git`` 是文件而非目录，也要能识别。"""
    (tmp_path / ".git").mkdir()
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / ".git").write_text("gitdir: ../.git/worktrees/inner\n", encoding="utf-8")
    assert find_repository_root(inner) == inner.resolve()


# --------------------------------------------------------------------------- #
# 遍历
# --------------------------------------------------------------------------- #
def test_walk_finds_python_files_sorted(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"b.py": "", "a.py": "", "c.txt": ""})
    result = walk_candidates(tmp_path, tmp_path)
    assert [entry.path for entry in result.entries] == ["a.py", "b.py"]
    assert result.files_seen == 3


def test_walk_prunes_default_excluded_dirs(tmp_path: Path) -> None:
    _make_tree(
        tmp_path,
        {"keep.py": "", "__pycache__/junk.py": "", ".git/hooks/x.py": ""},
    )
    result = walk_candidates(tmp_path, tmp_path, exclude_patterns=DEFAULT_EXCLUDES)
    assert [entry.path for entry in result.entries] == ["keep.py"]
    assert "__pycache__/" in result.excluded_dirs
    assert ".git/" in result.excluded_dirs


def test_walk_applies_custom_exclude(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "", "generated/b.py": ""})
    result = walk_candidates(tmp_path, tmp_path, exclude_patterns=["generated/"])
    assert [entry.path for entry in result.entries] == ["a.py"]


def test_walk_counts_excluded_files(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "", "b_skip.py": ""})
    result = walk_candidates(tmp_path, tmp_path, exclude_patterns=["*_skip.py"])
    assert [entry.path for entry in result.entries] == ["a.py"]
    assert result.files_excluded == 1


def test_walk_paths_are_relative_to_path_base(tmp_path: Path) -> None:
    """扫描子目录时，路径仍相对于 Git 工作区根——M2 与 M4 对齐的关键契约。"""
    _make_tree(tmp_path, {"pkg/mod.py": ""})
    result = walk_candidates(tmp_path / "pkg", tmp_path)
    assert [entry.path for entry in result.entries] == ["pkg/mod.py"]


def test_walk_respects_configured_suffixes(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "", "b.txt": ""})
    result = walk_candidates(tmp_path, tmp_path, include_suffixes=(".py", ".txt"))
    assert [entry.path for entry in result.entries] == ["a.py", "b.txt"]


def test_walk_is_deterministic(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"z.py": "", "a/y.py": "", "a/x.py": "", "m.py": ""})
    first = [entry.path for entry in walk_candidates(tmp_path, tmp_path).entries]
    second = [entry.path for entry in walk_candidates(tmp_path, tmp_path).entries]
    assert first == second == ["a/x.py", "a/y.py", "m.py", "z.py"]


def test_walk_flags_symlinked_file_without_following(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"real.py": "x = 1\n"})
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "real.py")
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")

    result = walk_candidates(tmp_path, tmp_path)
    flags = {entry.path: entry.is_symlink for entry in result.entries}
    assert flags["link.py"] is True
    assert flags["real.py"] is False


def test_walk_prunes_symlinked_directory(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"pkg/mod.py": ""})
    link = tmp_path / "linkdir"
    try:
        link.symlink_to(tmp_path / "pkg", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")

    result = walk_candidates(tmp_path, tmp_path)
    assert [entry.path for entry in result.entries] == ["pkg/mod.py"]
    assert "linkdir/" in result.excluded_dirs
