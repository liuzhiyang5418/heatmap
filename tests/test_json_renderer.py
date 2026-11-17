"""JSON output should expose the same result as the report."""

import json

from githotmap.core.diagnostics import AnalysisStats, Degradation, DegradationCode
from githotmap.core.models import AnalysisResult, FileMetrics, FileResult
from githotmap.renderers import registry


def test_json_renderer_serializes_result_without_losing_fields() -> None:
    result = AnalysisResult(
        repo_path=".", repo_urn="local:test", mode="hot",
        files=[FileResult(metrics=FileMetrics(path="\u76ee\u5f55/a.py", commits=2),
                          mode_score=42, status="low_confidence", confidence=0.5)],
    )
    assert "json" in registry.available()
    assert json.loads(registry.render(result, "json")) == result.to_dict()


def test_json_renderer_handles_empty_results() -> None:
    result = AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot")
    assert json.loads(registry.render(result, "json"))["files"] == []


def test_json_renderer_preserves_audit_counts_and_reasons() -> None:
    result = AnalysisResult(
        repo_path=".",
        repo_urn="local:test",
        mode="hot",
        stats=AnalysisStats(
            files_matched=2,
            files_emitted=1,
            files_degraded=1,
            degradations_by_code={"syntax-error": 1},
            degradations=[
                Degradation(
                    stage="scanner",
                    code=DegradationCode.SYNTAX_ERROR,
                    path="broken.py",
                    summary="file could not be parsed",
                )
            ],
        ),
    )

    payload = json.loads(registry.render(result, "json"))

    assert payload["stats"]["files_degraded"] == 1
    assert payload["stats"]["degradations_by_code"] == {"syntax-error": 1}
    assert payload["stats"]["degradations"][0]["path"] == "broken.py"
