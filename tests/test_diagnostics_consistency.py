"""原因码唯一来源与降级统计一致性校验（NFR-2 / 决策点 #1 收口）。

本文件锁定三件事：

1. ``DegradationCode`` 的扫描阶段码**直接引用** ``scanner.Limitation``，
   不是复制字面量——从根上消除两处各自漂移的可能；
2. ``scanner.LIMITATION_CODES`` 是 ``DegradationCode`` 的子集，
   且扩展码不会与扫描阶段码撞名；
3. 流水线的 ``AnalysisStats.degradations_by_code`` 与扫描器自身的
   ``ScanStats.degradations_by_code`` 对同一批文件**计数一致**，
   既不丢失、也不重复计数。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from githotmap.core.diagnostics import DegradationCode
from githotmap.core.pipeline import AnalysisPipeline
from githotmap.scanner import LIMITATION_CODES, Limitation, scan_repository

#: 扫描阶段对应的 6 个 DegradationCode，顺序与 scanner.Limitation 一致。
_SCAN_PHASE_CODES: tuple[DegradationCode, ...] = (
    DegradationCode.SYMLINK,
    DegradationCode.NOT_TEXT,
    DegradationCode.TOO_LARGE,
    DegradationCode.UNREADABLE,
    DegradationCode.UNSUPPORTED_LANGUAGE,
    DegradationCode.SYNTAX_ERROR,
)


def _make_faulty_repo(root: Path) -> Path:
    """建一个含「语法错误 + 二进制」两类扫描阶段降级的最小仓库。"""
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True)
    (repo / "ok.py").write_text("print(1)\n", encoding="utf-8")
    (repo / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    (repo / "bin.py").write_bytes(b"\x00\x01\x02binary")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-q", "-m", "fixture"],
        cwd=repo,
        check=True,
    )
    return repo


# --------------------------------------------------------------------------- #
# 1. 唯一来源：引用而非复制
# --------------------------------------------------------------------------- #
def test_scan_phase_codes_match_scanner_limitation() -> None:
    """扫描阶段码必须与 scanner.Limitation 同值同序。"""
    assert tuple(code.value for code in _SCAN_PHASE_CODES) == tuple(
        item.value for item in Limitation
    )
    assert tuple(code.value for code in _SCAN_PHASE_CODES) == LIMITATION_CODES


def test_limitation_codes_are_subset_of_degradation_codes() -> None:
    """scanner 的每个码都必须是 DegradationCode 的成员。"""
    assert set(LIMITATION_CODES) <= {code.value for code in DegradationCode}


def test_extension_codes_do_not_collide_with_scanner_codes() -> None:
    """扩展码与扫描阶段码互不重叠，避免语义混淆。"""
    extension = {code.value for code in DegradationCode} - set(LIMITATION_CODES)

    assert extension == {
        "git-quotepath",
        "stage-failed",
        "repo-not-git",
        "empty-repo",
        "shallow-clone",
    }


def test_degradation_code_is_str_enum_for_serialization() -> None:
    """Renderers/JSON 直接消费 .value，必须仍是 str 枚举。"""
    assert isinstance(DegradationCode.SYNTAX_ERROR, str)
    assert DegradationCode.SYNTAX_ERROR == "syntax-error"


# --------------------------------------------------------------------------- #
# 2. 两处统计数据一致（不丢、不重复）
# --------------------------------------------------------------------------- #
def test_pipeline_stats_match_scanner_stats(tmp_path: Path) -> None:
    """同一仓库上，AnalysisStats 与 ScanStats 对扫描阶段码的计数必须一致。"""
    repo = _make_faulty_repo(tmp_path)

    result = AnalysisPipeline().run(repo, limit=None)
    scan = scan_repository(repo)

    for code in LIMITATION_CODES:
        assert result.stats.degradations_by_code.get(code, 0) == (
            scan.stats.degradations_by_code[code]
        ), f"码 {code} 的计数不一致"


def test_degradation_counts_are_not_double_counted(tmp_path: Path) -> None:
    """若把 scan.stats 再叠加进 AnalysisStats，扫描阶段码会翻倍——本测试防回归。"""
    repo = _make_faulty_repo(tmp_path)

    result = AnalysisPipeline().run(repo, limit=None)

    expected_total = sum(len(item.limitations) for item in result.files)
    actual_total = sum(
        result.stats.degradations_by_code.get(code, 0) for code in LIMITATION_CODES
    )

    assert actual_total == expected_total
    assert result.stats.files_degraded == sum(1 for item in result.files if item.limitations)


def test_pipeline_reports_expected_codes_for_fault_repo(tmp_path: Path) -> None:
    """故障仓库应产出 syntax-error 与 not-text 各一处。"""
    repo = _make_faulty_repo(tmp_path)

    result = AnalysisPipeline().run(repo, limit=None)

    assert result.stats.degradations_by_code["syntax-error"] == 1
    assert result.stats.degradations_by_code["not-text"] == 1
    assert result.stats.files_degraded == 2
