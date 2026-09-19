"""Repository Scanner 门面层（``githotmap.scanner``）的集成测试。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from githotmap.scanner import (
    Limitation,
    RepositoryScanner,
    ScanConfig,
    ScanError,
    scan_repository,
)

#: 本仓库根目录，用于「扫描自己」的端到端断言。
REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _config(**overrides: object) -> ScanConfig:
    """默认关闭 Git 根探测，让 tmp_path 下的路径可预测。"""
    options: dict[str, object] = {"respect_git_root": False}
    options.update(overrides)
    return ScanConfig(**options)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 前置条件
# --------------------------------------------------------------------------- #
def test_scan_raises_on_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ScanError):
        scan_repository(tmp_path / "nope")


def test_scan_raises_on_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ScanError):
        scan_repository(target)


# --------------------------------------------------------------------------- #
# 基本行为
# --------------------------------------------------------------------------- #
def test_scan_reports_structure_and_prunes_noise(tmp_path: Path) -> None:
    _make_tree(
        tmp_path,
        {
            "pkg/mod.py": '"""文档。"""\n\n\ndef f(a):\n    if a:\n        return 1\n    return 0\n',
            "pkg/__pycache__/junk.py": "x = 1\n",
            "readme.txt": "hi\n",
        },
    )
    scan = scan_repository(tmp_path, _config())
    assert scan.paths() == ["pkg/mod.py"]

    item = scan.by_path()["pkg/mod.py"]
    assert item.parsed is True
    assert item.parse_error is None
    assert item.limitations == []
    assert item.symbol_count == 1
    assert item.function_count == 1
    assert item.class_count == 0
    assert item.lines.total == 7
    assert "pkg/__pycache__/" in scan.stats.excluded_dirs


def test_stats_invariants(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "x = 1\n", "skip/me.py": "y = 2\n", "b.txt": ""})
    scan = scan_repository(tmp_path, _config(exclude_patterns=["skip/"]))
    stats = scan.stats
    assert stats.files_matched == stats.files_emitted + stats.files_excluded
    assert stats.files_emitted == 1
    assert stats.files_parsed == 1
    assert stats.files_with_limitations == 0
    # 目录被剪枝时，其内部文件根本不会被逐个计数，只登记被剪掉的目录本身。
    assert stats.files_excluded == 0
    assert "skip/" in stats.excluded_dirs
    assert stats.total_bytes == scan.by_path()["a.py"].size_bytes


def test_excluded_files_are_counted_separately(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "x = 1\n", "b_skip.py": "y = 2\n"})
    scan = scan_repository(tmp_path, _config(exclude_patterns=["*_skip.py"]))
    stats = scan.stats
    assert scan.paths() == ["a.py"]
    assert stats.files_matched == 2
    assert stats.files_emitted == 1
    assert stats.files_excluded == 1


def test_hash_matches_file_content(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "x = 1\n"})
    scan = scan_repository(tmp_path, _config())
    # 按磁盘实际字节计算，避免 Windows 的 \n -> \r\n 文本模式转换影响断言。
    on_disk = (tmp_path / "a.py").read_bytes()
    item = scan.by_path()["a.py"]
    assert item.sha256 == hashlib.sha256(on_disk).hexdigest()
    assert item.size_bytes == len(on_disk)


def test_compute_hash_can_be_disabled(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "x = 1\n"})
    scan = scan_repository(tmp_path, _config(compute_hash=False))
    assert scan.by_path()["a.py"].sha256 is None


def test_scan_is_deterministic(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"b.py": "y = 2\n", "a.py": "x = 1\n", "c/d.py": "z = 3\n"})
    config = _config()
    first = scan_repository(tmp_path, config).paths()
    second = scan_repository(tmp_path, config).paths()
    assert first == second
    assert first == sorted(first)


def test_scanner_instance_is_reusable(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "x = 1\n"})
    scanner = RepositoryScanner(_config())
    assert scanner.name == "repository-scanner"
    assert scanner.scan(tmp_path).paths() == ["a.py"]
    assert scanner.scan(tmp_path).paths() == ["a.py"]


# --------------------------------------------------------------------------- #
# 路径基准（接口文档 §4.1 契约）
# --------------------------------------------------------------------------- #
def test_respect_git_root_uses_repo_root_as_path_base(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _make_tree(tmp_path, {"pkg/mod.py": "x = 1\n"})
    scan = scan_repository(tmp_path / "pkg")
    assert scan.paths() == ["pkg/mod.py"]
    assert Path(scan.path_base) == tmp_path.resolve()
    assert Path(scan.root) == (tmp_path / "pkg").resolve()


def test_respect_git_root_disabled_falls_back_to_scan_root(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _make_tree(tmp_path, {"pkg/mod.py": "x = 1\n"})
    scan = scan_repository(tmp_path / "pkg", _config())
    assert scan.paths() == ["mod.py"]
    assert Path(scan.path_base) == (tmp_path / "pkg").resolve()


# --------------------------------------------------------------------------- #
# 容错与模式
# --------------------------------------------------------------------------- #
def test_syntax_error_is_recorded_not_raised(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"broken.py": "def f(:\n    pass\n"})
    scan = scan_repository(tmp_path, _config())
    item = scan.by_path()["broken.py"]
    assert item.parsed is False
    assert item.parse_error is not None
    assert Limitation.SYNTAX_ERROR.value in item.limitations
    assert scan.stats.files_with_limitations == 1
    assert scan.stats.files_parsed == 0


def test_parse_structure_disabled_gives_coarse_line_counts(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": '"""文档。"""\n\nx = 1\n'})
    scan = scan_repository(tmp_path, _config(parse_structure=False))
    item = scan.by_path()["a.py"]
    assert item.parsed is False
    assert item.symbols == []
    assert item.imports == []
    assert item.limitations == []
    assert item.lines.total == 3
    assert item.lines.blank == 1
    assert item.lines.code == 2
    assert item.lines.comment == 0
    assert item.lines.docstring == 0


def test_symlinked_file_recorded_with_limitation(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"real.py": "x = 1\n"})
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "real.py")
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")

    scan = scan_repository(tmp_path, _config())
    item = scan.by_path()["link.py"]
    assert item.parsed is False
    assert item.size_bytes == 0
    assert item.sha256 is None
    assert Limitation.SYMLINK.value in item.limitations


# --------------------------------------------------------------------------- #
# 序列化
# --------------------------------------------------------------------------- #
def test_to_dict_is_json_serializable(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"a.py": "def f():\n    return 1\n"})
    scan = scan_repository(tmp_path, _config())
    payload = json.loads(json.dumps(scan.to_dict()))
    assert payload["files"][0]["path"] == "a.py"
    assert payload["files"][0]["symbols"][0]["name"] == "f"
    assert payload["files"][0]["symbols"][0]["cyclomatic_complexity"] == 1
    assert payload["stats"]["files_emitted"] == 1
    assert payload["path_base"] == str(tmp_path.resolve())


# --------------------------------------------------------------------------- #
# 扫描本项目自身（端到端）
# --------------------------------------------------------------------------- #
def test_scan_self_finds_scanner_modules() -> None:
    scan = scan_repository(REPO_ROOT)
    paths = set(scan.paths())
    assert "src/githotmap/scanner/models.py" in paths
    assert "src/githotmap/scanner/walker.py" in paths
    assert "src/githotmap/scanner/parser.py" in paths
    assert "src/githotmap/scanner/scanner.py" in paths
    assert "src/githotmap/core/models.py" in paths


def test_scan_self_excludes_git_directory() -> None:
    """本仓库 ``.git`` 下的内容不能出现在扫描结果里。

    注意：在 git worktree / submodule 中 ``.git`` 是**文件**而非目录，此时走的是
    「非 ``.py`` 后缀被跳过」而不是「目录剪枝」的路径，因此这里**不**断言
    ``excluded_dirs`` 的具体内容——目录剪枝行为由
    ``tests/test_scanner_walker.py::test_walk_prunes_default_excluded_dirs`` 专门覆盖。
    """
    scan = scan_repository(REPO_ROOT)
    assert all(not path.startswith(".git") for path in scan.paths())


def test_scan_self_paths_follow_posix_convention() -> None:
    scan = scan_repository(REPO_ROOT)
    for path in scan.paths():
        assert "\\" not in path
        assert not path.startswith("./")
        assert not path.startswith("/")


def test_scan_self_parses_every_file_without_limitations() -> None:
    """本项目全部源码都应解析成功——失败会让 CI 立刻暴露问题。"""
    scan = scan_repository(REPO_ROOT)
    assert scan.stats.files_emitted > 0
    failed = [item.path for item in scan.files if not item.parsed]
    assert failed == [], f"以下文件未能解析: {failed}"
    assert scan.stats.files_parsed == scan.stats.files_emitted
    assert scan.stats.files_with_limitations == 0


def test_scan_self_line_counts_invariant() -> None:
    scan = scan_repository(REPO_ROOT)
    for item in scan.files:
        counts = item.lines
        assert counts.total == (
            counts.code + counts.comment + counts.docstring + counts.blank
        ), f"{item.path} 行数分类不满足不变量"


def test_scan_self_reports_own_package_metrics() -> None:
    """对已知文件做一次「黄金值」断言，防止解析逻辑被静默改坏。"""
    scan = scan_repository(REPO_ROOT)
    by_path = scan.by_path()
    models = by_path["src/githotmap/scanner/models.py"]
    qualnames = {symbol.qualname for symbol in models.symbols}
    assert {"LineCounts", "SymbolInfo", "FileStructure", "ScanStats", "RepositoryScan"} <= qualnames
    assert "FileStructure.to_dict" in qualnames
    assert models.imports == [
        "__future__",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
    ]
