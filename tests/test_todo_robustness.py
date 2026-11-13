"""NFR-2 故障注入测试（todo 阶段）——对应 NFR 计划 WP-3 中 M3 协作的场景。

每个场景断言三件事（验收指标 NFR-2.1 / NFR-2.2）：

1. 不抛未捕获异常（崩溃率为 0）；
2. 每条降级记录都带非空原因码，且与预期一致（原因码覆盖率 100%）；
3. 检测结果（todos / degradations）正确。

与 M6 主责的 ``tests/test_robustness.py``（全流水线级）互补：本文件聚焦
**M2 scanner → M3 todo 的端到端契约**，除读取失败场景外均使用真实
``scan_repository`` 构造输入，避免"自己 mock 自己"。

场景编号沿用 NFR 计划 §2 WP-3 的 12 类清单（#2/#3/#4/#5/#6/#10 与 todo 相关）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from githotmap.scanner import FileStructure, RepositoryScan, scan_repository
from githotmap.todo import TodoDetector
from githotmap.todo.models import TodoScan


def _detect(root: Path) -> TodoScan:
    """真实扫描 + 检测的端到端入口（M2 → M3）。"""
    return TodoDetector().detect(scan_repository(str(root)))


def _assert_codes(result: TodoScan, expected: dict[str, str]) -> None:
    """NFR-2.2：所有降级必带非空 code，且指定路径的 code 与预期一致。"""
    assert all(d.code for d in result.degradations), "存在无原因码的降级记录"
    actual = {d.path: d.code for d in result.degradations}
    for path, code in expected.items():
        assert actual.get(path) == code, f"{path}: 期望 {code}，实际 {actual.get(path)}"


def test_normal_repo_has_no_degradation(tmp_path):
    """基线：干净文件既不产生降级也不误报。"""
    (tmp_path / "ok.py").write_text("# TODO: fine\nx = 1\n", encoding="utf-8")

    result = _detect(tmp_path)

    assert result.total_count == 1
    assert result.degradations == []


def test_binary_file_skipped_with_code(tmp_path):
    """场景 #2 二进制 .py：scanner 标 not-text，detector 跳过并记录原因码。"""
    (tmp_path / "binary.py").write_bytes(b"\x00\x01TODO: inside binary\xff\xfe")
    (tmp_path / "ok.py").write_text("# TODO: fine\n", encoding="utf-8")

    result = _detect(tmp_path)

    # 二进制里的 TODO 不检出；正常文件不受影响；降级带 not-text。
    assert all(t.path != "binary.py" for t in result.todos)
    assert any(t.path == "ok.py" for t in result.todos)
    _assert_codes(result, {"binary.py": "not-text"})


def test_large_file_skipped_with_code(tmp_path):
    """场景 #3 超过 2MB：scanner 标 too-large，埋在里面的 TODO 不读、不崩。"""
    with open(tmp_path / "large.py", "w", encoding="utf-8") as fh:
        fh.write("# TODO: buried in big file\n")
        fh.write("x = 1\n" * 400000)  # ~2.4MB，超过默认 max_file_bytes=2_000_000

    result = _detect(tmp_path)

    assert all(t.path != "large.py" for t in result.todos)
    _assert_codes(result, {"large.py": "too-large"})


def test_syntax_error_file_still_scanned(tmp_path):
    """场景 #4 语法错误 .py：todo 阶段不降级（文件可读），降级路径仍能提取真注释。

    scanner 侧的 ``syntax-error`` 是它的 parse 事实（记在 FileStructure.parse_error），
    不阻断 todo 读取，因此 todo 侧不产生降级记录。
    """
    (tmp_path / "broken.py").write_text(
        "def broken(:\n# TODO: still here\n", encoding="utf-8"
    )

    result = _detect(tmp_path)

    assert any(
        t.path == "broken.py" and t.description == "still here" for t in result.todos
    )
    assert result.degradations == []


def test_gbk_encoded_file_no_crash(tmp_path):
    """场景 #5 GBK 编码声明：utf-8 容错读取不崩溃，ASCII 标记仍可检出。

    中文描述会因 ``errors="replace"`` 变乱码——属已知口径问题 **M3-8**
    （待与 M2 会签统一到 ``tokenize.open``），此处只验收 NFR-2 的健壮性：
    不崩溃、不漏掉 ASCII 标记、不产生错误降级。
    """
    (tmp_path / "gbk.py").write_bytes(
        b"# -*- coding: gbk -*-\n" + ("# TODO: " + "中文注释待办").encode("gbk") + b"\n"
    )

    result = _detect(tmp_path)

    assert any(t.path == "gbk.py" and t.kind.value == "TODO" for t in result.todos)
    assert result.degradations == []


def test_symlink_skipped_with_code(tmp_path):
    """场景 #6 符号链接：scanner 标 symlink，detector 不跟随并记录原因码。

    Windows 下创建符号链接常需管理员/开发者模式——按 NFR 计划 §6 风险表
    标记为 skip（只记 skip 不记失败），与全仓库现有 3 个 skip 同源。
    """
    target = tmp_path / "real.py"
    target.write_text("# TODO: real\n", encoding="utf-8")
    link = tmp_path / "link.py"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"platform cannot create symlinks: {type(exc).__name__}")

    result = _detect(tmp_path)

    assert all(t.path != "link.py" for t in result.todos)
    _assert_codes(result, {"link.py": "symlink"})


def test_missing_file_degrades_with_code(tmp_path):
    """场景 #10a 读取失败（路径不存在）：跳过 + unreadable，正常文件不受影响。

    scanner 不会列出不存在的路径，此处手工构造 RepositoryScan 精确注入该故障。
    """
    (tmp_path / "ok.py").write_text("# TODO: fine\n", encoding="utf-8")
    scan = RepositoryScan(
        root=str(tmp_path),
        path_base=str(tmp_path),
        files=[FileStructure(path="missing.py"), FileStructure(path="ok.py")],
    )

    result = TodoDetector().detect(scan)

    assert [t.path for t in result.todos] == ["ok.py"]
    _assert_codes(result, {"missing.py": "unreadable"})


def test_directory_path_degrades_with_code(tmp_path):
    """场景 #10b 路径指向目录（IsADirectoryError）：同样降级不崩。"""
    (tmp_path / "ok.py").write_text("# TODO: fine\n", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    scan = RepositoryScan(
        root=str(tmp_path),
        path_base=str(tmp_path),
        files=[FileStructure(path="subdir"), FileStructure(path="ok.py")],
    )

    result = TodoDetector().detect(scan)

    assert [t.path for t in result.todos] == ["ok.py"]
    _assert_codes(result, {"subdir": "unreadable"})


def test_fault_scan_is_deterministic(tmp_path):
    """NFR-3 附带验收：同一故障仓两次检测的 ``to_dict()`` 逐字节相同。

    ``TodoScan`` 不含时间字段，因此断言整体相等（而非仅排除字段）。
    """
    (tmp_path / "binary.py").write_bytes(b"\x00TODO: inside")
    (tmp_path / "ok.py").write_text("# TODO: fine\n", encoding="utf-8")

    first = _detect(tmp_path).to_dict()
    second = _detect(tmp_path).to_dict()

    assert first == second
