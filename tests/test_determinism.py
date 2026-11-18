"""Deterministic serialization and fingerprint contract (NFR-3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from githotmap.clock import FixedClock
from githotmap.core.models import AnalysisResult, FileMetrics, FileResult
from githotmap.core.pipeline import AnalysisPipeline


_INSTANT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def test_canonical_and_fingerprint_ignore_runtime_and_host_metadata(tmp_path) -> None:
    from tests.test_pipeline_degradation import _make_repo

    repo = _make_repo(tmp_path)
    first = AnalysisPipeline(clock=FixedClock(_INSTANT)).run(repo)
    second = AnalysisPipeline(clock=FixedClock(_INSTANT)).run(repo)

    assert first.canonical() == second.canonical()
    assert first.fingerprint() == second.fingerprint()
    assert len(first.fingerprint()) == 64
    deterministic = first.to_dict(deterministic=True)
    assert "analyzed_at" not in deterministic
    assert "stage_elapsed_ms" not in deterministic["stats"]
    assert "repo_path" in deterministic


def test_canonical_rounds_floats_and_normalizes_paths() -> None:
    result = AnalysisResult(
        repo_path="C:\\work\\repo",
        repo_urn="local:C:\\work\\repo",
        mode="hot",
        files=[
            FileResult(
                metrics=FileMetrics(path="src\\main.py", commits=1.12345678),
                mode_score=4.12345678,
            )
        ],
    )

    payload = json.loads(result.canonical())
    assert payload["files"][0]["path"] == "src/main.py"
    assert payload["files"][0]["metrics"]["commits"] == 1.123457
    assert "repo_path" not in payload
    assert "repo_urn" not in payload


def test_canonical_rejects_non_finite_numbers() -> None:
    import pytest

    result = AnalysisResult(
        repo_path=".",
        repo_urn="local:test",
        mode="hot",
        files=[FileResult(metrics=FileMetrics(path="a.py", commits=float("nan")))],
    )

    with pytest.raises(ValueError, match="NaN"):
        result.canonical()


def test_schema_version_is_serialized() -> None:
    result = AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot")
    assert result.to_dict()["schema_version"] == "1.0"


def test_file_metrics_are_serialized_and_deterministically_normalized() -> None:
    result = AnalysisResult(
        repo_path=".",
        repo_urn="local:test",
        mode="hot",
        files=[FileResult(metrics=FileMetrics(path="src\\a.py", churn=1.23456789))],
    )

    assert result.to_dict()["files"][0]["metrics"]["churn"] == 1.23456789
    assert result.to_dict(deterministic=True)["files"][0]["metrics"]["churn"] == 1.234568
