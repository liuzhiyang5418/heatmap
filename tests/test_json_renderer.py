"""JSON output should expose the same result as the report."""

import json

from githotmap.core.models import AnalysisResult, FileMetrics, FileResult
from githotmap.renderers import registry


def test_json_renderer_serializes_result_without_losing_fields() -> None:
    result = AnalysisResult(
        repo_path=".", repo_urn="local:test", mode="hot",
        files=[FileResult(metrics=FileMetrics(path="目录/a.py", commits=2),
                          mode_score=42, status="low_confidence", confidence=0.5)],
    )
    assert "json" in registry.available()
    assert json.loads(registry.render(result, "json")) == result.to_dict()


def test_json_renderer_handles_empty_results() -> None:
    result = AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot")
    assert json.loads(registry.render(result, "json"))["files"] == []
