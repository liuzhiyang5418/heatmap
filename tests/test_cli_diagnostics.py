"""CLI 诊断输出与覆盖率导出（Sprint 3 / WP-S3-3）。

覆盖 Sprint 3「调试与维护支持」的三项交付：

- ``--verbose``：阶段耗时 + 降级明细，且每条降级都带**处置建议**；
- ``--report-coverage``：把 ``AnalysisStats`` 导出成 JSON，供 CI 归档；
- ``remediation_hint``：每个原因码都必须有建议（新增码漏写会在这里失败）。
"""

from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

from githotmap.cli.main import main
from githotmap.core.diagnostics import DegradationCode, remediation_hint


def _repository(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir()
    with git.Repo.init(root) as repo:
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        repo.index.add(list(files))
        actor = git.Actor("Fixture", "fixture@example.invalid")
        repo.index.commit("add fixtures", author=actor, committer=actor)
    return root


def _clean_repo(root: Path) -> Path:
    return _repository(root / "clean", {"src/main.py": b"def f():\n    return 1\n"})


def _faulty_repo(root: Path) -> Path:
    return _repository(
        root / "faulty",
        {"src/ok.py": b"print(1)\n", "src/broken.py": b"def broken(:\n    pass\n"},
    )


# --------------------------------------------------------------------------- #
# 处置建议映射
# --------------------------------------------------------------------------- #
def test_every_degradation_code_has_a_hint() -> None:
    """每个原因码都必须有可执行建议——新增码漏写会在这里失败。"""
    missing = [code.value for code in DegradationCode if "未登记" in remediation_hint(code)]
    assert missing == [], f"以下原因码缺少处置建议: {missing}"


def test_unknown_code_falls_back_without_raising() -> None:
    hint = remediation_hint("no-such-code")

    assert "未登记" in hint


def test_hint_accepts_plain_string_values() -> None:
    """允许直接传 .value（测试与外部脚本常用），与传枚举等价。"""
    assert remediation_hint("syntax-error") == remediation_hint(DegradationCode.SYNTAX_ERROR)


# --------------------------------------------------------------------------- #
# --verbose
# --------------------------------------------------------------------------- #
def test_verbose_prints_stage_timings_and_degradation_hints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _faulty_repo(tmp_path)
    out = tmp_path / "report.html"

    code = main(
        ["analyze", "--repo-path", str(repo), "--verbose", "--output-file", str(out)]
    )

    assert code == 0
    stderr = capsys.readouterr().err
    assert "阶段耗时" in stderr
    assert "降级明细" in stderr
    assert "syntax-error" in stderr
    # 处置建议的标志：每条降级后面跟一行 "→ ..."
    assert "→" in stderr


def test_verbose_on_clean_repo_reports_no_degradation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _clean_repo(tmp_path)
    out = tmp_path / "report.html"

    code = main(
        ["analyze", "--repo-path", str(repo), "--verbose", "--output-file", str(out)]
    )

    assert code == 0
    stderr = capsys.readouterr().err
    assert "降级明细: 无" in stderr


def test_without_verbose_stderr_stays_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """默认不输出诊断——诊断信息不能污染正常使用的 stderr。"""
    repo = _faulty_repo(tmp_path)
    out = tmp_path / "report.html"

    code = main(["analyze", "--repo-path", str(repo), "--output-file", str(out)])

    assert code == 0
    assert "阶段耗时" not in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# --report-coverage
# --------------------------------------------------------------------------- #
def test_report_coverage_writes_parseable_json(tmp_path: Path) -> None:
    repo = _faulty_repo(tmp_path)
    coverage_path = tmp_path / "coverage.json"
    out = tmp_path / "report.html"

    code = main(
        [
            "analyze",
            "--repo-path",
            str(repo),
            "--report-coverage",
            str(coverage_path),
            "--output-file",
            str(out),
        ]
    )

    assert code == 0
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    assert {
        "files_matched",
        "files_emitted",
        "files_degraded",
        "commits_seen",
        "degradations_by_code",
        "stage_elapsed_ms",
        "degradations",
    } <= set(payload)
    assert payload["degradations_by_code"].get("syntax-error") == 1
    assert payload["files_degraded"] == 1


def test_report_coverage_and_verbose_can_be_combined(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _clean_repo(tmp_path)
    coverage_path = tmp_path / "coverage.json"
    out = tmp_path / "report.html"

    code = main(
        [
            "analyze",
            "--repo-path",
            str(repo),
            "--report-coverage",
            str(coverage_path),
            "--verbose",
            "--output-file",
            str(out),
        ]
    )

    assert code == 0
    assert coverage_path.is_file()
    assert "阶段耗时" in capsys.readouterr().err
