"""风险等级校准（P2）的状态、置信度、阈值与自适应上限测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import githotmap.core.pipeline as pipeline_module
from githotmap.config.config import COMPOSITE_WEIGHTS, ScoringConfig
from githotmap.core.models import CompositeMode, FileMetrics, FileResult, ScoringMode
from githotmap.core.pipeline import AnalysisPipeline
from githotmap.core.scoring import _apply_recency_demotion, apply_composite, score_file, score_grade


def make_metrics(**overrides: Any) -> FileMetrics:
    defaults: dict[str, Any] = {
        "path": "src/main.py",
        "size_bytes": 10000,
        "lines_of_code": 500.0,
        "commits": 100.0,
        "churn": 2000.0,
        "recent_commits": 20.0,
        "recent_churn": 500.0,
        "unique_contributors": 5.0,
        "age_days": 300.0,
        "gini": 0.3,
        "decayed_commits": 40.0,
        "decayed_churn": 800.0,
    }
    defaults.update(overrides)
    return FileMetrics(**defaults)


def high_risk_metrics(**overrides: Any) -> FileMetrics:
    """构造各 HOT 信号均饱和、默认应得 critical 的指标。"""
    values: dict[str, Any] = {
        "size_bytes": 500 * 1024,
        "lines_of_code": 10000.0,
        "commits": 500.0,
        "churn": 5000.0,
        "recent_commits": 500.0,
        "recent_churn": 5000.0,
        "unique_contributors": 20.0,
        "age_days": 3650.0,
        "decayed_commits": 500.0,
        "decayed_churn": 5000.0,
    }
    values.update(overrides)
    return make_metrics(**values)


@pytest.mark.parametrize(
    ("commits", "minimum", "expected"),
    [
        (0.0, 3.0, 0.3),
        (1.0, 3.0, 1.0 / 3.0),
        (2.0, 3.0, 2.0 / 3.0),
        (3.0, 3.0, 1.0),
        (9.0, 3.0, 1.0),
        (5.0, 10.0, 0.5),
    ],
)
def test_confidence_uses_commit_sample_size(
    commits: float, minimum: float, expected: float
) -> None:
    cfg = ScoringConfig(min_commits_for_confidence=minimum)
    result = score_file(make_metrics(commits=commits), ScoringMode.HOT, cfg)

    assert result.confidence == pytest.approx(expected)
    assert result.status == ("low_confidence" if commits < minimum else "ok")


def test_missing_metrics_override_confidence_and_zero_all_scores() -> None:
    result = score_file(make_metrics(size_bytes=0, commits=100.0), ScoringMode.HOT, _cfg())

    assert result.status == "missing"
    assert result.confidence == 0.0
    assert set(result.scores.values()) == {0.0}
    assert set(result.severities.values()) == {"low"}


def test_status_and_confidence_are_serialized_for_renderers() -> None:
    result = score_file(make_metrics(commits=1.0), ScoringMode.HOT, _cfg())
    data = result.to_dict()

    assert data["status"] == "low_confidence"
    assert data["confidence"] == pytest.approx(1.0 / 3.0)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100.0, "critical"),
        (90.0, "critical"),
        (89.99, "high"),
        (70.0, "high"),
        (69.99, "medium"),
        (40.0, "medium"),
        (39.99, "low"),
        (10.0, "low"),
    ],
)
def test_custom_severity_thresholds_include_lower_bounds(score: float, expected: str) -> None:
    # 故意使用非等级顺序的字典，验证实现按阈值而不是插入顺序判定。
    thresholds = {"low": 10.0, "medium": 40.0, "critical": 90.0, "high": 70.0}

    assert score_grade(score, thresholds) == expected


def test_custom_thresholds_are_applied_to_base_modes() -> None:
    cfg = ScoringConfig(
        severity_thresholds={"critical": 100.0, "high": 0.0, "medium": 0.0, "low": 0.0}
    )
    result = score_file(high_risk_metrics(), ScoringMode.HOT, cfg)

    assert result.scores[ScoringMode.HOT.value] == pytest.approx(100.0)
    assert result.severities[ScoringMode.HOT.value] == "critical"


def test_custom_thresholds_are_applied_to_composite_modes() -> None:
    result = FileResult(metrics=make_metrics())
    result.scores[ScoringMode.COMPLEXITY.value] = 50.0
    result.scores[ScoringMode.ROI.value] = 50.0

    apply_composite(
        result,
        CompositeMode.REFACTOR_NOW,
        COMPOSITE_WEIGHTS[CompositeMode.REFACTOR_NOW],
        thresholds={"critical": 50.0, "high": 25.0, "medium": 10.0, "low": 0.0},
    )

    assert result.mode_score == pytest.approx(50.0)
    assert result.severities[CompositeMode.REFACTOR_NOW.value] == "critical"


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("critical", "high"),
        ("high", "medium"),
        ("medium", "low"),
        ("low", "low"),
    ],
)
def test_low_recency_demotes_exactly_one_level(severity: str, expected: str) -> None:
    assert _apply_recency_demotion(severity, recency_signal=0.09, threshold_low=0.1) == expected


def test_recency_equal_to_threshold_does_not_demote() -> None:
    assert _apply_recency_demotion("critical", recency_signal=0.1, threshold_low=0.1) == "critical"


def test_recency_demotion_updates_severity_reasoning() -> None:
    result = score_file(
        high_risk_metrics(recent_commits=0.0, recent_churn=0.0), ScoringMode.HOT, _cfg()
    )

    assert result.scores[ScoringMode.HOT.value] == pytest.approx(100.0)
    assert result.severities[ScoringMode.HOT.value] == "high"
    reasons = result.reasoning[ScoringMode.HOT.value]
    assert reasons[0].startswith("Severity: high")
    assert "已按近因降档" in reasons[0]
    assert all("Severity: critical" not in reason for reason in reasons)


def capture_pipeline_caps(
    monkeypatch: pytest.MonkeyPatch,
    metrics_map: dict[str, FileMetrics],
    config: ScoringConfig,
) -> ScoringConfig:
    """运行隔离的流水线，并捕获实际传给评分引擎的临时配置。"""
    captured: list[ScoringConfig] = []

    monkeypatch.setattr(
        pipeline_module,
        "aggregate_file_metrics",
        lambda *args, **kwargs: metrics_map,
    )
    monkeypatch.setattr(pipeline_module, "enrich_worktree_attributes", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline_module, "resolve_urn", lambda path: "local:test")

    def fail_scan(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("测试不需要真实扫描器")

    monkeypatch.setattr(pipeline_module, "scan_repository", fail_scan)

    def fake_score_file(
        metrics: FileMetrics, mode: ScoringMode, scoring_cfg: ScoringConfig
    ) -> FileResult:
        captured.append(scoring_cfg)
        return FileResult(metrics=metrics)

    monkeypatch.setattr(pipeline_module, "score_file", fake_score_file)
    pipeline = AnalysisPipeline(config)
    monkeypatch.setattr(pipeline.history, "collect", lambda *args, **kwargs: [])

    pipeline.run(Path("."), limit=None)
    assert captured
    return captured[0]


def test_adaptive_caps_use_pipeline_p90_and_preserve_other_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = {
        f"src/file_{value}.py": make_metrics(
            path=f"src/file_{value}.py",
            commits=float(value),
            churn=float(value * 10),
            lines_of_code=float(value * 100),
            size_bytes=value * 1024,
        )
        for value in range(1, 11)
    }
    original = ScoringConfig(
        enable_adaptive_caps=True,
        normalization_caps={"commits": 999.0, "recent": 7.0},
    )

    scoring_cfg = capture_pipeline_caps(monkeypatch, metrics, original)

    # 当前流水线采用 int(n * 0.90) 的零基索引；n=10 时取排序后的最后一项。
    assert scoring_cfg.normalization_caps["commits"] == 10.0
    assert scoring_cfg.normalization_caps["churn"] == 100.0
    assert scoring_cfg.normalization_caps["loc"] == 1000.0
    assert scoring_cfg.normalization_caps["size_kb"] == 10.0
    assert scoring_cfg.normalization_caps["recent"] == 7.0
    assert original.normalization_caps == {"commits": 999.0, "recent": 7.0}


def test_adaptive_caps_floor_zero_valued_metrics_at_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = {
        "src/empty.py": make_metrics(
            path="src/empty.py", commits=0.0, churn=0.0, lines_of_code=0.0, size_bytes=0
        )
    }

    scoring_cfg = capture_pipeline_caps(
        monkeypatch, metrics, ScoringConfig(enable_adaptive_caps=True)
    )

    assert scoring_cfg.normalization_caps["commits"] == 1.0
    assert scoring_cfg.normalization_caps["churn"] == 1.0
    assert scoring_cfg.normalization_caps["loc"] == 1.0
    assert scoring_cfg.normalization_caps["size_kb"] == 1.0


def test_disabled_adaptive_caps_keep_explicit_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = {"src/main.py": make_metrics(commits=100.0)}
    original = ScoringConfig(
        enable_adaptive_caps=False,
        normalization_caps={"commits": 123.0, "churn": 456.0},
    )

    scoring_cfg = capture_pipeline_caps(monkeypatch, metrics, original)

    assert scoring_cfg.normalization_caps == {"commits": 123.0, "churn": 456.0}
    assert scoring_cfg is not original


def _cfg() -> ScoringConfig:
    return ScoringConfig()
