"""WP-0 公共诊断模型及 AnalysisResult 契约测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from githotmap.core.diagnostics import AnalysisStats, Degradation, DegradationCode
from githotmap.core.models import AnalysisResult, FileMetrics, FileResult


def test_degradation_codes_cover_the_nfr2_contract() -> None:
    assert {code.value for code in DegradationCode} == {
        "symlink",
        "not-text",
        "too-large",
        "unreadable",
        "unsupported-language",
        "syntax-error",
        "git-quotepath",
        "stage-failed",
        "repo-not-git",
        "empty-repo",
        "shallow-clone",
    }


def test_degradation_to_dict_uses_json_native_values() -> None:
    degradation = Degradation(
        stage="scanner",
        code=DegradationCode.TOO_LARGE,
        path="src/large.py",
        summary="file exceeds the size limit",
    )

    assert degradation.to_dict() == {
        "stage": "scanner",
        "code": "too-large",
        "path": "src/large.py",
        "summary": "file exceeds the size limit",
        "detail": None,
    }
    assert json.loads(json.dumps(degradation.to_dict())) == degradation.to_dict()


def test_analysis_stats_serializes_counts_timings_and_degradations() -> None:
    degradation = Degradation(
        stage="git",
        code=DegradationCode.SHALLOW_CLONE,
        path="a" * 40,
        summary="diff unavailable at shallow boundary",
        detail="parent object is unavailable",
    )
    stats = AnalysisStats(
        files_matched=12,
        files_emitted=10,
        files_degraded=2,
        commits_seen=7,
        stage_elapsed_ms={"git": 12.5, "scoring": 3.0},
        degradations_by_code={"shallow-clone": 1},
        degradations=[degradation],
    )

    payload = stats.to_dict()

    assert payload["files_matched"] == 12
    assert payload["files_emitted"] == 10
    assert payload["files_degraded"] == 2
    assert payload["commits_seen"] == 7
    assert payload["stage_elapsed_ms"] == {"git": 12.5, "scoring": 3.0}
    assert payload["degradations_by_code"] == {"shallow-clone": 1}
    assert payload["degradations"][0]["code"] == "shallow-clone"
    assert payload["degradations"][0]["detail"] == "parent object is unavailable"


def test_mutable_diagnostic_defaults_are_not_shared() -> None:
    first = AnalysisStats()
    second = AnalysisStats()
    first.stage_elapsed_ms["git"] = 1.0
    first.degradations_by_code["empty-repo"] = 1
    first.degradations.append(
        Degradation(
            stage="git",
            code=DegradationCode.EMPTY_REPO,
            path=None,
            summary="repository has no commits",
        )
    )

    assert second.stage_elapsed_ms == {}
    assert second.degradations_by_code == {}
    assert second.degradations == []


def test_analysis_result_exposes_schema_version_and_stats() -> None:
    result = AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot")

    assert result.schema_version == "1.0"
    assert isinstance(result.stats, AnalysisStats)
    payload = result.to_dict()
    assert payload["schema_version"] == "1.0"
    assert payload["stats"] == AnalysisStats().to_dict()


def test_analysis_result_default_stats_are_not_shared() -> None:
    first = AnalysisResult(repo_path=".", repo_urn="local:first", mode="hot")
    second = AnalysisResult(repo_path=".", repo_urn="local:second", mode="hot")

    first.stats.files_matched = 3

    assert second.stats.files_matched == 0


def test_file_result_limitations_are_independent_and_serialized() -> None:
    first = FileResult(metrics=FileMetrics(path="src/first.py"))
    second = FileResult(metrics=FileMetrics(path="src/second.py"))

    first.limitations.append("syntax-error")

    assert second.limitations == []
    assert first.to_dict()["limitations"] == ["syntax-error"]
    assert second.to_dict()["limitations"] == []


def test_complete_analysis_result_is_json_serializable() -> None:
    file_result = FileResult(
        metrics=FileMetrics(path="src/main.py"),
        limitations=["not-text"],
    )
    result = AnalysisResult(
        repo_path=".",
        repo_urn="local:test",
        mode="hot",
        files=[file_result],
        stats=AnalysisStats(
            files_matched=1,
            files_emitted=1,
            files_degraded=1,
            degradations_by_code={"not-text": 1},
            degradations=[
                Degradation(
                    stage="scanner",
                    code=DegradationCode.NOT_TEXT,
                    path="src/main.py",
                    summary="binary file skipped",
                )
            ],
        ),
    )

    payload = result.to_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_diagnostics_import_does_not_load_config() -> None:
    """公共诊断契约必须可独立导入，避免 config ⇄ core 循环。"""
    src = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import githotmap.core.diagnostics; "
                "assert 'githotmap.config.config' not in sys.modules"
            ),
        ],
        check=True,
        env=env,
        capture_output=True,
    )
