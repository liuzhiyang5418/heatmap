"""评分引擎：把 ``FileMetrics`` 转换为 ``FileResult``。

热图主循环只需调用 :func:`score_file`，其余函数均为内部工具。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from githotmap.config.config import DEFAULT_WEIGHTS, ScoringConfig
from githotmap.core.models import (
    BreakdownKey,
    CompositeMode,
    FileMetrics,
    FileResult,
    ScoringMode,
)

if TYPE_CHECKING:
    pass  # 避免循环导入，实际无额外类型引用。

# ---- 全局默认 caps（来自参考工具 hotspot 默认配置）----
# 当仓库规模远超这些上限时，评分会饱和；可通过 ScoringConfig.normalization_caps 微调。
DEFAULT_CAPS: dict[str, float] = {
    "commits": 100.0,
    "churn": 1000.0,
    "loc": 1000.0,
    "size_kb": 100.0,
    "contrib": 5.0,
    "age_days": 365.0,
    "cc": 20.0,
    "nesting": 5.0,
    "symbols": 50.0,
    "imports": 30.0,
    "todo_density": 1.0,
}

# ---- 风险等级阈值（可配置化，保留 backward-compatible 默认值）----
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "critical": 75.0,
    "high": 50.0,
    "medium": 25.0,
    "low": 0.0,
}

# 近因联动：当 recency 低于阈值时 severity 降档
_DEMOTION_CHAIN: dict[str, str] = {
    "critical": "high",
    "high": "medium",
    "medium": "low",
    "low": "low",
}


def _norm(value: float, cap: float) -> float:
    """把原始指标归一化到 [0,1]，使用指定上限做饱和。"""
    return min(1.0, value / cap)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """把值限制在 [lo,hi] 区间内。"""
    return max(lo, min(hi, value))


def score_grade(score: float, thresholds: dict[str, float] | None = None) -> str:
    """把 0–100 分数映射为自然语言风险等级。

    阈值规则：critical ≥ 75, high ≥ 50, medium ≥ 25, low ≥ 0。
    支持通过 ``thresholds`` 参数注入自定义阈值（用于仓库校准后冻结）。
    """
    th = thresholds or _DEFAULT_THRESHOLDS
    if score >= th.get("critical", 75.0):
        return "critical"
    if score >= th.get("high", 50.0):
        return "high"
    if score >= th.get("medium", 25.0):
        return "medium"
    return "low"


def _reasoning_template(mode: ScoringMode) -> list[str]:
    """返回各模式对应的关键维度理由模板。"""
    templates: dict[ScoringMode, list[str]] = {
        ScoringMode.HOT: ["活跃提交", "高代码变动"],
        ScoringMode.RISK: ["贡献者集中", "低近期活跃度", "高 Gini 系数"],
        ScoringMode.COMPLEXITY: ["高圈复杂度", "深嵌套深度", "多符号定义"],
        ScoringMode.ROI: ["高代码变动", "大量行数", "高 Gini"],
    }
    return templates.get(mode, [])


def compute_score(
    mode: ScoringMode,
    metrics: FileMetrics,
    config: ScoringConfig,
) -> tuple[float, dict[str, float], list[str], float]:
    """为单一模式计算综合得分与分解。

    返回 (score, breakdown, reasoning, recency_signal)。
    """
    # 缺失文件处理：如果 size_bytes == 0，说明文件已删除或不存在于工作区。
    if metrics.size_bytes == 0:
        return 0.0, {}, [], 0.0

    weights = config.weights_for(mode)
    if not weights:
        return 0.0, {}, [], 0.0

    # 使用用户或自适应 caps（ScoringConfig.normalization_caps 可覆盖 DEFAULT_CAPS）。
    caps = dict(DEFAULT_CAPS)
    caps.update(config.normalization_caps)

    # ---- 计算各信号分量 ----
    commits_norm = _norm(metrics.commits, caps["commits"])
    churn_norm = _norm(metrics.churn, caps["churn"])
    loc_norm = _norm(metrics.lines_of_code, caps["loc"])
    size_norm = _norm(metrics.size_bytes / 1024.0, caps["size_kb"])
    contrib_norm = _norm(metrics.unique_contributors, caps["contrib"])
    age_norm = _norm(metrics.age_days, caps["age_days"])
    recency_norm = (
        _norm(metrics.recent_commits, caps["commits"])
        + _norm(metrics.recent_churn, caps["churn"])
    ) / 2.0
    inv_contrib_norm = 1.0 - contrib_norm  # 贡献者越少越危险
    gini_norm = metrics.gini
    low_recent_norm = 1.0 - recency_norm  # 近期越不活跃越危险
    cc_norm = _norm(metrics.max_cyclomatic_complexity, caps["cc"])
    nesting_norm = _norm(metrics.max_nesting_depth, caps["nesting"])
    symbols_norm = _norm(metrics.symbol_count, caps["symbols"])
    imports_norm = _norm(metrics.import_count, caps["imports"])
    todo_density = metrics.todo_count / max(metrics.lines_of_code, 1.0)
    todo_density_norm = _norm(todo_density, caps["todo_density"])

    # ---- 按权重加权 ----
    signal_map: dict[BreakdownKey, float] = {
        BreakdownKey.COMMITS: commits_norm,
        BreakdownKey.CHURN: churn_norm,
        BreakdownKey.CONTRIB: contrib_norm,
        BreakdownKey.AGE: age_norm,
        BreakdownKey.SIZE: size_norm,
        BreakdownKey.LOC: loc_norm,
        BreakdownKey.INV_CONTRIB: inv_contrib_norm,
        BreakdownKey.GINI: gini_norm,
        BreakdownKey.LOW_RECENT: low_recent_norm,
        BreakdownKey.CC: cc_norm,
        BreakdownKey.NESTING: nesting_norm,
        BreakdownKey.SYMBOLS: symbols_norm,
        BreakdownKey.IMPORTS: imports_norm,
        BreakdownKey.TODO_DENSITY: todo_density_norm,
    }

    score = 0.0
    breakdown: dict[str, float] = {}
    for key, weight in weights.items():
        val = signal_map.get(key, 0.0)
        score += val * weight
        breakdown[key.value] = val * weight

    score *= 100.0

    # ---- 构建理由（取贡献最大的前 3 项）----
    sorted_reasons = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    reasoning: list[str] = []
    for key_name, contrib in sorted_reasons[:3]:
        if contrib <= 0.0:
            continue
        # 简单映射为可读理由
        reasoning.append(f"{key_name} 贡献 {contrib:.1%}")

    if not reasoning:
        reasoning = _reasoning_template(mode)

    return score, breakdown, reasoning, recency_norm


def score_file(
    metrics: FileMetrics,
    mode: ScoringMode,
    config: ScoringConfig,
) -> FileResult:
    """对单个文件进行**全部四种**基础模式评分，并包装为 :class:`FileResult`。"""
    result = FileResult(
        metrics=metrics,
        recency_threshold_low=config.recency_threshold_low,
        recency_threshold_high=config.recency_threshold_high,
    )

    # 阈值与置信度参数
    thresholds = config.severity_thresholds or _DEFAULT_THRESHOLDS
    min_commits = max(config.min_commits_for_confidence, 1.0)

    for m in ScoringMode:
        score, breakdown, reasoning, recency = compute_score(m, metrics, config)
        result.scores[m.value] = score
        result.breakdowns[m.value] = breakdown
        result.reasoning[m.value] = reasoning

        # 计算 severity
        severity = score_grade(score, thresholds)
        # 近因联动：recency 低于 threshold_low 时降一档
        if recency < config.recency_threshold_low:
            severity = _DEMOTION_CHAIN.get(severity, severity)
        result.severities[m.value] = severity

        # 记录 recency_signal（用于后续复合模式或 UI 展示）
        if m == mode:
            result.recency_signal = recency

    # 小样本置信度：提交数不足时线性降级 [0.3, 1.0]
    confidence = _clamp(metrics.commits / min_commits, 0.3, 1.0)
    result.confidence = confidence

    # 缺失数据状态：size_bytes == 0 时标记 missing
    if metrics.size_bytes == 0:
        result.status = "missing"
        result.confidence = 0.0
    elif confidence < 1.0:
        result.status = "low_confidence"
    else:
        result.status = "ok"

    # 汇总状态：取所有模式中最差的 severity
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    worst_severity = max(
        result.severities.values(),
        key=lambda s: severity_order.get(s, 0),
        default="low",
    )

    result.mode_score = result.scores[mode.value]
    return result


def apply_composite(
    file_result: FileResult,
    weights: list[tuple[ScoringMode, float]],
) -> None:
    """基于已有基础模式分数，计算复合模式分数并覆盖 ``mode_score``。"""
    if not weights:
        return

    total_weight = sum(w for _, w in weights)
    if total_weight == 0.0:
        return

    score = 0.0
    breakdown: dict[str, float] = {}
    reasoning: list[str] = []
    severities: list[str] = []

    for base_mode, weight in weights:
        ratio = weight / total_weight
        mode_score = file_result.scores.get(base_mode.value, 0.0)
        score += mode_score * ratio

        # 合并 breakdown（按比例缩放）
        base_breakdown = file_result.breakdowns.get(base_mode.value, {})
        for key, val in base_breakdown.items():
            breakdown[key] = breakdown.get(key, 0.0) + val * ratio

        # 合并 reasoning
        base_reasoning = file_result.reasoning.get(base_mode.value, [])
        reasoning.extend(base_reasoning)

        severities.append(file_result.severities.get(base_mode.value, "low"))

    composite_mode = "+".join(m.value for m, _ in weights)
    file_result.scores[composite_mode] = score
    file_result.breakdowns[composite_mode] = breakdown
    file_result.reasoning[composite_mode] = reasoning[:5]  # 限制长度
    file_result.severities[composite_mode] = score_grade(score)
    file_result.mode_score = score
