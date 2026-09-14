"""评分引擎的单元测试。"""

from __future__ import annotations

import pytest

from githotmap.config.config import COMPOSITE_WEIGHTS, ScoringConfig
from githotmap.core.models import CompositeMode, FileMetrics, FileResult, ScoringMode
from githotmap.core.scoring import (
    compute_composite_score,
    compute_recency_signal,
    compute_score,
    score_file,
)


def make_metrics(**overrides) -> FileMetrics:
    defaults = dict(
        path="src/main.py",
        size_bytes=10000,
        lines_of_code=500.0,
        commits=100.0,
        churn=2000.0,
        recent_commits=20.0,
        recent_churn=500.0,
        unique_contributors=5.0,
        age_days=300.0,
        gini=0.3,
        decayed_commits=40.0,
        decayed_churn=800.0,
    )
    defaults.update(overrides)
    return FileMetrics(**defaults)  # type: ignore[arg-type]


def _cfg() -> ScoringConfig:
    return ScoringConfig()


def test_score_within_bounds_for_all_modes() -> None:
    cfg = _cfg()
    m = make_metrics()
    for mode in ScoringMode:
        sr = compute_score(
            m, mode, cfg.weights_for(mode), cfg.recency_threshold_low, cfg.recency_threshold_high
        )
        assert 0.0 <= sr.score <= 100.0
        assert sr.recency_signal is not None


def test_empty_file_scores_zero() -> None:
    cfg = _cfg()
    m = make_metrics(size_bytes=0)
    sr = compute_score(
        m, ScoringMode.HOT, cfg.weights_for(ScoringMode.HOT), 0.1, 0.4
    )
    assert sr.score == 0.0


def test_test_file_is_debuffed() -> None:
    cfg = _cfg()
    normal = compute_score(
        make_metrics(), ScoringMode.HOT, cfg.weights_for(ScoringMode.HOT), 0.1, 0.4
    )
    test = compute_score(
        make_metrics(path="src/test_main.py"),
        ScoringMode.HOT,
        cfg.weights_for(ScoringMode.HOT),
        0.1,
        0.4,
    )
    assert test.score == pytest.approx(normal.score * 0.5)


def test_recency_signal_blend() -> None:
    m = make_metrics(commits=10.0, recent_commits=5.0, churn=100.0, recent_churn=30.0)
    # 0.7 * (5/10) + 0.3 * (30/100) = 0.35 + 0.09 = 0.44
    assert compute_recency_signal(m) == pytest.approx(0.44)


def test_composite_blend_is_weighted_average() -> None:
    f = FileResult(metrics=make_metrics())
    f.scores[ScoringMode.HOT.value] = 60.0
    f.scores[ScoringMode.RISK.value] = 40.0
    score, _ = compute_composite_score(
        f, CompositeMode.ACTIVE_OWNERS, COMPOSITE_WEIGHTS[CompositeMode.ACTIVE_OWNERS]
    )
    assert score == pytest.approx(50.0)


def test_score_file_populates_all_base_modes() -> None:
    f = score_file(make_metrics(), ScoringMode.HOT, _cfg())
    assert set(f.scores) == {m.value for m in ScoringMode}
    assert f.mode_score == f.scores[ScoringMode.HOT.value]
    assert f.breakdowns  # 非空
