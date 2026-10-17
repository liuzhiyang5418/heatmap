"""``githotmap.todo.detector`` 的单元测试。

覆盖：多文件聚合、路径规范、确定性排序、字符串内假标记在聚合时也被排除。
"""

from __future__ import annotations

from githotmap.scanner import FileStructure, RepositoryScan
from githotmap.todo.detector import TodoDetector


def _make_scan(root: str, paths: list[str]) -> RepositoryScan:
    """构造一个最小可用的 RepositoryScan（files 只填 path，供 detector 使用）。"""
    return RepositoryScan(
        root=root,
        path_base=root,
        files=[FileStructure(path=p) for p in paths],
    )


def test_detect_multiple_files(tmp_path):
    """聚合多个文件，且字符串里的假标记在聚合时也被排除。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("# TODO: fix\nx = 1\n", encoding="utf-8")
    (src / "b.py").write_text("msg = 'FIXME: not a comment'\n# HACK: ok\n", encoding="utf-8")

    scan = _make_scan(str(tmp_path), ["src/a.py", "src/b.py"])
    result = TodoDetector().detect(scan)

    assert result.path_base == str(tmp_path)
    # a.py 有 1 个 TODO；b.py 的 FIXME 在字符串里被排除，只剩 1 个 HACK。
    assert len(result.todos) == 2
    assert result.todos[0].path == "src/a.py"
    assert result.todos[1].path == "src/b.py"
    assert result.todos[1].kind.value == "HACK"


def test_deterministic_order(tmp_path):
    """输出按 (path, lineno, column) 升序，保证可复现。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "b.py").write_text("# FIXME: b\n# TODO: b2\n", encoding="utf-8")
    (src / "a.py").write_text("# TODO: a\n", encoding="utf-8")

    scan = _make_scan(str(tmp_path), ["src/a.py", "src/b.py"])
    result = TodoDetector().detect(scan)

    # 路径升序：src/a.py 在前；同文件按行号升序。
    assert [t.path for t in result.todos] == ["src/a.py", "src/b.py", "src/b.py"]
    assert [t.kind.value for t in result.todos] == ["TODO", "FIXME", "TODO"]


def test_empty_scan():
    """无文件时返回空结果且不报错。"""
    result = TodoDetector().detect(_make_scan("/tmp", []))
    assert result.todos == []


def test_to_dict_json_native(tmp_path):
    """to_dict() 返回值只含 JSON 原生类型（可 json.dumps）。"""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("# TODO: fix\nx = 1\n", encoding="utf-8")

    scan = _make_scan(str(tmp_path), ["src/a.py"])
    result = TodoDetector().detect(scan)
    import json

    payload = result.to_dict()
    json.dumps(payload)
    assert isinstance(payload["todos"], list)
    assert len(result.todos) == 1
    assert payload["total_count"] == 1
    assert payload["counts_by_kind"]["TODO"] == 1


def test_scan_convenience_methods(tmp_path):
    """测试面向 M5/M6 的便捷聚合统计接口。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("# TODO: one\n# FIXME: two\n", encoding="utf-8")
    (src / "b.py").write_text("# TODO: three\n", encoding="utf-8")

    scan = _make_scan(str(tmp_path), ["src/a.py", "src/b.py"])
    result = TodoDetector().detect(scan)

    # 1. total_count 属性
    assert result.total_count == 3

    # 2. paths() 去重且升序
    assert result.paths() == ["src/a.py", "src/b.py"]

    # 3. by_path() 字典索引
    by_path = result.by_path()
    assert len(by_path["src/a.py"]) == 2
    assert len(by_path["src/b.py"]) == 1
    assert [t.kind.value for t in by_path["src/a.py"]] == ["TODO", "FIXME"]

    # 4. count_by_kind() 分类计数
    kinds = result.count_by_kind()
    assert kinds["TODO"] == 2
    assert kinds["FIXME"] == 1
    assert kinds["HACK"] == 0
    assert kinds["XXX"] == 0

    # 5. count_by_path() 文件级计数
    by_path_counts = result.count_by_path()
    assert by_path_counts == {"src/a.py": 2, "src/b.py": 1}

