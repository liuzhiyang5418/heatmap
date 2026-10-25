"""评分引擎的单元测试。"""

from __future__ import annotations

import pytest

from githotmap.config.config import COMPOSITE_WEIGHTS, ScoringConfig
from githotmap.core.models import CompositeMode, FileMetrics, FileResult, ScoringMode
from githotmap.core.scoring import (
    DEFAULT_CAPS,
    _normalize_blend,
    _normalize_weights,
    apply_composite,
    compute_composite_score,
    compute_recency_signal,
    compute_score,
    score_file,
    score_files,
    score_grade,
)


def make_metrics(**overrides) -> FileMetrics:
    defaults = {
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


def test_score_files_batch_matches_single() -> None:
    cfg = _cfg()
    ms = [make_metrics(), make_metrics(path="src/other.py")]
    results = score_files(ms, ScoringMode.ROI, cfg)
    assert len(results) == 2
    for f in results:
        assert f.mode_score == f.scores[ScoringMode.ROI.value]


def test_risk_mode_test_file_debuff_is_milder() -> None:
    cfg = _cfg()
    normal = compute_score(
        make_metrics(), ScoringMode.RISK, cfg.weights_for(ScoringMode.RISK), 0.1, 0.4
    )
    test = compute_score(
        make_metrics(path="tests/test_x.py"),
        ScoringMode.RISK,
        cfg.weights_for(ScoringMode.RISK),
        0.1,
        0.4,
    )
    assert test.score == pytest.approx(normal.score * 0.75)


def test_config_ext_debuff_only_for_complexity() -> None:
    cfg = _cfg()
    normal = compute_score(
        make_metrics(), ScoringMode.COMPLEXITY, cfg.weights_for(ScoringMode.COMPLEXITY), 0.1, 0.4
    )
    cfg_file = compute_score(
        make_metrics(path="config.yaml"),
        ScoringMode.COMPLEXITY,
        cfg.weights_for(ScoringMode.COMPLEXITY),
        0.1,
        0.4,
    )
    assert cfg_file.score == pytest.approx(normal.score * 0.5)
    hot_cfg_file = compute_score(
        make_metrics(path="config.yaml"),
        ScoringMode.HOT,
        cfg.weights_for(ScoringMode.HOT),
        0.1,
        0.4,
    )
    assert hot_cfg_file.score > 0.0


def test_hot_uses_decayed_but_risk_uses_totals() -> None:
    """hot 对 commits 使用衰减量，risk 使用累计量。"""
    cfg = _cfg()
    m = make_metrics(commits=100.0, decayed_commits=10.0, churn=2000.0, decayed_churn=200.0)
    hot = compute_score(m, ScoringMode.HOT, cfg.weights_for(ScoringMode.HOT), 0.1, 0.4)
    risk = compute_score(m, ScoringMode.RISK, cfg.weights_for(ScoringMode.RISK), 0.1, 0.4)
    # hot 的 commits 分解应为 10/500 = 0.02
    assert hot.breakdown.get("commits") == pytest.approx(2.0)
    # risk 的 churn 分解应为 2000/5000 = 0.4
    assert risk.breakdown.get("churn") == pytest.approx(40.0)


def test_normalize_blend_fallback_on_invalid_weights() -> None:
    blend = [(ScoringMode.HOT, 0.0), (ScoringMode.RISK, 0.5)]
    weights = _normalize_blend(blend)
    assert weights == {ScoringMode.HOT: 0.5, ScoringMode.RISK: 0.5}


def test_normalize_blend_normalizes_to_sum_one() -> None:
    blend = [(ScoringMode.HOT, 2.0), (ScoringMode.RISK, 6.0)]
    weights = _normalize_blend(blend)
    assert weights[ScoringMode.HOT] == pytest.approx(0.25)
    assert weights[ScoringMode.RISK] == pytest.approx(0.75)


def test_apply_composite_writes_score_breakdown_reasoning() -> None:
    f = score_file(make_metrics(), ScoringMode.HOT, _cfg())
    apply_composite(
        f, CompositeMode.REFACTOR_NOW, COMPOSITE_WEIGHTS[CompositeMode.REFACTOR_NOW]
    )
    key = CompositeMode.REFACTOR_NOW.value
    assert key in f.scores
    assert f.mode_score == f.scores[key]
    assert key in f.breakdowns
    reasons = f.reasoning[key]
    assert reasons and reasons[0].startswith("Composite Score:")
    # 配比头部应标注组成模式
    assert "complexity 60%" in reasons[0] and "roi 40%" in reasons[0]


def test_composite_score_never_exceeds_bounds() -> None:
    f = FileResult(metrics=make_metrics())
    f.scores[ScoringMode.COMPLEXITY.value] = 100.0
    f.scores[ScoringMode.ROI.value] = 100.0
    score, _ = compute_composite_score(
        f, CompositeMode.REFACTOR_NOW, COMPOSITE_WEIGHTS[CompositeMode.REFACTOR_NOW]
    )
    assert score <= 100.0


def test_recency_reasoning_active_vs_historical() -> None:
    cfg = _cfg()
    # 近期活跃：recency_signal 高（hot 的 churn 分解来自衰减量，故同步抬高）
    active = make_metrics(
        churn=6000.0, decayed_churn=4000.0, recent_commits=90.0, recent_churn=5900.0
    )
    sr_active = compute_score(
        active, ScoringMode.HOT, cfg.weights_for(ScoringMode.HOT), 0.1, 0.4
    )
    assert any("当前开发瓶颈" in r for r in sr_active.reasoning)
    # 历史热点：recent 接近 0
    stale = make_metrics(
        churn=6000.0, decayed_churn=4000.0, recent_commits=0.0, recent_churn=0.0
    )
    sr_stale = compute_score(
        stale, ScoringMode.HOT, cfg.weights_for(ScoringMode.HOT), 0.1, 0.4
    )
    assert any("近期已趋稳定" in r for r in sr_stale.reasoning)


def test_score_grade_thresholds() -> None:
    assert score_grade(80.0) == "critical"
    assert score_grade(75.0) == "critical"
    assert score_grade(60.0) == "high"
    assert score_grade(30.0) == "medium"
    assert score_grade(0.0) == "low"


def test_normalize_weights_scales_to_sum_one() -> None:
    from githotmap.core.models import BreakdownKey

    w = _normalize_weights({BreakdownKey.CHURN: 2.0, BreakdownKey.LOC: 2.0})
    assert sum(w.values()) == pytest.approx(1.0)
    # 负权重按 0 处理
    w2 = _normalize_weights({BreakdownKey.CHURN: -1.0, BreakdownKey.LOC: 3.0})
    assert w2[BreakdownKey.CHURN] == 0.0
    assert w2[BreakdownKey.LOC] == pytest.approx(1.0)


def test_unnormalized_weights_do_not_inflate_score() -> None:
    """权重和不等于 1 时分数仍应保持 0–100 语义（同一文件两种配权结果一致）。"""
    cfg = _cfg()
    m = make_metrics()
    w1 = cfg.weights_for(ScoringMode.HOT)
    w2 = {k: v * 7 for k, v in w1.items()}  # 放大 7 倍
    s1 = compute_score(m, ScoringMode.HOT, w1, 0.1, 0.4).score
    s2 = compute_score(m, ScoringMode.HOT, w2, 0.1, 0.4).score
    assert s1 == pytest.approx(s2)


def test_custom_caps_affect_normalization() -> None:
    cfg = _cfg()
    m = make_metrics(commits=100.0, decayed_commits=100.0)
    default = compute_score(m, ScoringMode.HOT, cfg.weights_for(ScoringMode.HOT), 0.1, 0.4)
    # 把 commits 上限调低到 100：commits 信号应饱和为 1.0（默认 500 时仅 0.2）
    capped = compute_score(
        m,
        ScoringMode.HOT,
        cfg.weights_for(ScoringMode.HOT),
        0.1,
        0.4,
        caps={"commits": 100.0},
    )
    assert capped.breakdown["commits"] == pytest.approx(100.0)
    assert default.breakdown["commits"] == pytest.approx(20.0)
    # 未指定的键回退默认值
    assert DEFAULT_CAPS["churn"] == 5000.0


def test_score_file_populates_severities() -> None:
    f = score_file(make_metrics(), ScoringMode.HOT, _cfg())
    assert set(f.severities) == {m.value for m in ScoringMode}
    assert f.severities[ScoringMode.HOT.value] in {"critical", "high", "medium", "low"}


def test_high_score_gets_severity_reason_prefix() -> None:
    cfg = _cfg()
    m = make_metrics()  # churn/decayed 都高
    sr = compute_score(m, ScoringMode.HOT, cfg.weights_for(ScoringMode.HOT), 0.1, 0.4)
    if sr.severity in ("critical", "high"):
        assert sr.reasoning[0].startswith("Severity:")


def test_composite_severity_written() -> None:
    f = score_file(make_metrics(), ScoringMode.HOT, _cfg())
    apply_composite(
        f, CompositeMode.LEGACY_DEBT, COMPOSITE_WEIGHTS[CompositeMode.LEGACY_DEBT]
    )
    assert f.severities[CompositeMode.LEGACY_DEBT.value] in {
        "critical", "high", "medium", "low",
    }
