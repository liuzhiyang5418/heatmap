"""扫描器原因码契约测试（NFR-2.2 原因码覆盖率 / WP-0 原因码对齐）。

本文件锁定三件事：

1. **取值稳定**：``Limitation`` 的 6 个取值是跨模块契约，改动会同时破坏
   ``core/diagnostics.DegradationCode``、M6 的展示映射与 NFR-3 的冻结指纹；
2. **结构稳定**：``ScanStats.degradations_by_code`` 的键集合与顺序固定为
   :data:`~githotmap.scanner.LIMITATION_CODES`，未命中的码记 0；
3. **覆盖完整**：扫描器产出的每一个 limitation 都必须是已登记的码，
   且按码计数与逐文件 limitations 对得上（不静默丢失降级）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from githotmap.scanner import (
    LIMITATION_CODES,
    Limitation,
    RepositoryScanner,
    ScanConfig,
    ScanStats,
    scan_repository,
)

# 硬编码的期望值：故意不复用枚举，才能发现「有人改了枚举」。
_EXPECTED_CODES: tuple[str, ...] = (
    "symlink",
    "not-text",
    "too-large",
    "unreadable",
    "unsupported-language",
    "syntax-error",
)


def _config(**overrides: object) -> ScanConfig:
    base = ScanConfig(compute_hash=False)
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


# --------------------------------------------------------------------------- #
# 契约稳定性
# --------------------------------------------------------------------------- #
def test_limitation_values_are_frozen() -> None:
    """取值被锁定：改值会让 M5 的 DegradationCode 与历史指纹同时失配。"""
    assert tuple(code.value for code in Limitation) == _EXPECTED_CODES


def test_limitation_codes_constant_matches_enum_order() -> None:
    """唯一来源常量必须与枚举的定义顺序一致（顺序即 to_dict 的键序）。"""
    assert LIMITATION_CODES == _EXPECTED_CODES


def test_limitation_codes_has_no_duplicates() -> None:
    assert len(set(LIMITATION_CODES)) == len(LIMITATION_CODES)


# --------------------------------------------------------------------------- #
# ScanStats 结构稳定性
# --------------------------------------------------------------------------- #
def test_default_stats_zeroes_every_code() -> None:
    """未命中任何降级时，结构仍然是完整的 6 个键。"""
    stats = ScanStats()

    assert tuple(stats.degradations_by_code.keys()) == LIMITATION_CODES
    assert set(stats.degradations_by_code.values()) == {0}


def test_stats_to_dict_key_order_is_stable() -> None:
    """to_dict 按 LIMITATION_CODES 输出，与传入 dict 的插入顺序无关。"""
    stats = ScanStats(degradations_by_code={"syntax-error": 2, "symlink": 1})

    payload = stats.to_dict()["degradations_by_code"]

    assert tuple(payload.keys()) == LIMITATION_CODES
    assert payload["syntax-error"] == 2
    assert payload["symlink"] == 1
    assert payload["not-text"] == 0


def test_stats_to_dict_is_json_native() -> None:
    stats = ScanStats(degradations_by_code={"syntax-error": 1})

    json.dumps(stats.to_dict())  # 不抛错即通过


def test_stats_counts_agree_with_file_limitations(tmp_path: Path) -> None:
    """按码计数必须等于逐文件 limitations 的实际出现次数（NFR-2.2 不静默丢失）。"""
    (tmp_path / "bad.py").write_bytes(b"def broken(:\n    pass\n")
    (tmp_path / "bin.py").write_bytes(b"\x00\x01binary")
    (tmp_path / "ok.py").write_text("print(1)\n", encoding="utf-8")

    scan = scan_repository(tmp_path, _config())
    expected: dict[str, int] = {}
    for item in scan.files:
        for code in item.limitations:
            expected[code] = expected.get(code, 0) + 1

    for code in LIMITATION_CODES:
        assert scan.stats.degradations_by_code[code] == expected.get(code, 0)


# --------------------------------------------------------------------------- #
# 故障注入：每类降级都要被正确归类
# --------------------------------------------------------------------------- #
def test_scan_counts_each_degradation_code(tmp_path: Path) -> None:
    """构造四类可稳定复现的降级，断言各自被归到正确的码。"""
    (tmp_path / "broken.py").write_bytes(b"def broken(:\n    pass\n")  # 语法错误
    (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02binary")  # 二进制
    (tmp_path / "huge.py").write_bytes(b"x" * 4096)  # 超过上限
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")  # 非 Python

    config = _config(include_suffixes=(".py", ".md"), max_file_bytes=1024)
    scan = RepositoryScanner(config).scan(tmp_path)
    by_code = scan.stats.degradations_by_code

    assert by_code["syntax-error"] == 1
    assert by_code["not-text"] == 1
    assert by_code["too-large"] == 1
    assert by_code["unsupported-language"] == 1
    assert by_code["symlink"] == 0
    assert by_code["unreadable"] == 0
    assert scan.stats.files_with_limitations == 4


def test_symlinked_file_counted_under_symlink_code(tmp_path: Path) -> None:
    (tmp_path / "real.py").write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "real.py")
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")

    scan = scan_repository(tmp_path, _config())

    assert scan.stats.degradations_by_code["symlink"] == 1
    assert scan.stats.files_with_limitations == 1


def test_every_emitted_limitation_is_a_registered_code(tmp_path: Path) -> None:
    """扫描器不得产出未登记的码，否则下游的展示与统计会静默漏项。"""
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "b.py").write_bytes(b"\x00")
    (tmp_path / "c.py").write_bytes(b"def bad(:\n")
    (tmp_path / "d.md").write_text("x\n", encoding="utf-8")

    scan = scan_repository(tmp_path, _config(include_suffixes=(".py", ".md")))

    for item in scan.files:
        assert set(item.limitations) <= set(LIMITATION_CODES)


def test_clean_scan_reports_no_degradation(tmp_path: Path) -> None:
    """干净仓库的降级计数必须全为 0（避免把正常文件误报成降级）。"""
    (tmp_path / "ok.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    scan = scan_repository(tmp_path, _config())

    assert scan.stats.files_with_limitations == 0
    assert set(scan.stats.degradations_by_code.values()) == {0}


def test_self_scan_only_emits_registered_codes() -> None:
    """对本仓库自身扫描，同样不能出现未登记的码。"""
    repo_root = Path(__file__).resolve().parent.parent

    scan = scan_repository(repo_root)

    for item in scan.files:
        assert set(item.limitations) <= set(LIMITATION_CODES)
