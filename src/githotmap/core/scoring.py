"""评分引擎：四种基础模式 + 三种复合模式的 0–100 分计算、分解与理由生成。

算法对齐参考工具 hotspot 的 ``core/algo/score.go``：

- 各指标先按可调上限归一化到 [0,1]，再按模式权重加权求和；
- ``hot``/``roi`` 对 commits/churn 使用**指数衰减**后的近期量，突出当前瓶颈；
- 对测试/自动生成/示例/配置文件施加降权（debuff），避免噪声抬高评分；
- 每个文件附带 ``recency_signal`` 与动态阈值，用于区分"当前活跃"与"历史热点"。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from githotmap.core.metrics import clamp
from githotmap.core.models import BreakdownKey, CompositeMode, FileMetrics, FileResult, ScoringMode

# 归一化上限默认值：超过该值即饱和。可通过 compute_score 的 ``caps`` 参数按仓库规模覆盖
#（例如大型仓库可调高 _MAX_COMMITS / _MAX_CHURN，避免大量文件同时饱和失去区分度）。
DEFAULT_CAPS: dict[str, float] = {
    "contrib": 20.0,
    "commits": 500.0,
    "size_kb": 500.0,
    "age_days": 3650.0,
    "churn": 5000.0,
    "recent": 50.0,
    "loc": 10000.0,
}

# 风险等级阈值（分，含下限）：分数 -> critical/high/medium/low。
SEVERITY_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (75.0, "critical"),
    (50.0, "high"),
    (25.0, "medium"),
    (0.0, "low"),
)

# 近因信号的提交/改动权重：提交权重更高，避免单次大规模重排格式提交过度抬升信号。
_COMMIT_RECENCY_WEIGHT = 0.7
_CHURN_RECENCY_WEIGHT = 0.3

_CONFIG_EXTS = {
    "yml", "yaml", "json", "toml", "cfg", "xml", "ini",
    "lock", "sum", "csv", "tsv", "md", "txt", "tfstate",
}
_DEBUFF_SUBSTRINGS = ("test", "generate", "example", "mock")

_BASE_MODES = (ScoringMode.HOT, ScoringMode.RISK, ScoringMode.COMPLEXITY, ScoringMode.ROI)


@dataclass(slots=True)
class ScoreResult:
    """单一评分模式的完整产出。"""

    score: float
    breakdown: dict[BreakdownKey, float]  # 各信号的百分比贡献
    reasoning: list[str]
    recency_signal: float
    severity: str = "low"  # critical / high / medium / low，见 score_grade()


def score_grade(score: float) -> str:
    """把 0–100 分映射为风险等级：critical / high / medium / low。"""
    for threshold, label in SEVERITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "low"


def _normalize_weights(weights: dict[BreakdownKey, float]) -> dict[BreakdownKey, float]:
    """把模式权重归一化到和为 1，保证分数稳定在 0–100 语义。

    权重为空或总和非法（<=0）时原样返回，由调用方决定如何处理（此时得分趋近 0）。
    """
    total = sum(w for w in weights.values() if w > 0)
    if total <= 0:
        return weights
    return {key: max(w, 0.0) / total for key, w in weights.items()}


def compute_recency_signal(metrics: FileMetrics) -> float:
    """计算近因信号 [0,1]：近期提交/改动占生命周期总量的加权比例。"""
    commit_ratio = metrics.recent_commits / metrics.commits if metrics.commits > 0 else 0.0
    churn_ratio = metrics.recent_churn / metrics.churn if metrics.churn > 0 else 0.0
    return clamp(commit_ratio * _COMMIT_RECENCY_WEIGHT + churn_ratio * _CHURN_RECENCY_WEIGHT)


def compute_score(
    metrics: FileMetrics,
    mode: ScoringMode,
    weights: dict[BreakdownKey, float],
    threshold_low: float,
    threshold_high: float,
    caps: dict[str, float] | None = None,
) -> ScoreResult:
    """计算单文件在指定模式下的分数、分解与理由。

    ``caps`` 可覆盖 :data:`DEFAULT_CAPS` 中的归一化上限（缺省键回退默认值）。
    权重内部会归一化到和为 1，因此自定义权重无需手工配平。
    """
    if metrics.size_bytes == 0:
        return ScoreResult(0.0, {}, [], 0.0)

    c = {**DEFAULT_CAPS, **(caps or {})}
    weights = _normalize_weights(weights)

    # ---- 归一化指标 [0,1] ----
    n_contrib = clamp(metrics.unique_contributors / c["contrib"])
    n_commits = clamp(metrics.commits / c["commits"])
    n_size = clamp((metrics.size_bytes / 1024.0) / c["size_kb"])
    n_age = clamp(math.log1p(metrics.age_days) / math.log1p(c["age_days"]))
    n_churn = clamp(metrics.churn / c["churn"])
    n_loc = clamp(metrics.lines_of_code / c["loc"])
    n_decayed_commits = clamp(metrics.decayed_commits / c["commits"])
    n_decayed_churn = clamp(metrics.decayed_churn / c["churn"])
    n_gini = clamp(metrics.gini)
    n_inv_contrib = clamp(1.0 - n_contrib)
    n_recent_commits = clamp(metrics.recent_commits / c["recent"])
    n_low_recent = clamp(1.0 - n_recent_commits)

    recency_signal = compute_recency_signal(metrics)

    # ---- 模式选择提交/改动指标：hot/roi 采用衰减后的近期量 ----
    if mode in (ScoringMode.HOT, ScoringMode.ROI):
        final_commits = n_decayed_commits
        final_churn = n_decayed_churn
    else:
        final_commits = n_commits
        final_churn = n_churn

    # ---- 组装加权分解 ----
    norm = {
        BreakdownKey.AGE: n_age,
        BreakdownKey.CHURN: final_churn,
        BreakdownKey.COMMITS: final_commits,
        BreakdownKey.CONTRIB: n_contrib,
        BreakdownKey.SIZE: n_size,
    }
    if mode == ScoringMode.RISK:
        norm.update(
            {
                BreakdownKey.GINI: n_gini,
                BreakdownKey.INV_CONTRIB: n_inv_contrib,
                BreakdownKey.LOC: n_loc,
                BreakdownKey.LOW_RECENT: n_low_recent,
            }
        )
    elif mode == ScoringMode.COMPLEXITY:
        norm.update({BreakdownKey.LOC: n_loc, BreakdownKey.LOW_RECENT: n_low_recent})
    elif mode == ScoringMode.ROI:
        norm.update({BreakdownKey.GINI: n_gini, BreakdownKey.LOC: n_loc})

    raw = 0.0
    for key, value in norm.items():
        raw += weights.get(key, 0.0) * value
    score = raw * 100.0

    # ---- 降权：测试/自动生成/示例/配置文件（两项独立，可叠加）----
    path_lower = metrics.path.lower()
    ext = os.path.splitext(metrics.path)[1].lower().lstrip(".")
    if any(s in path_lower for s in _DEBUFF_SUBSTRINGS):
        score *= 0.75 if mode == ScoringMode.RISK else 0.50
    if ext in _CONFIG_EXTS and mode == ScoringMode.COMPLEXITY:
        score *= 0.50

    breakdown = {key: value * 100.0 for key, value in norm.items() if weights.get(key, 0.0) != 0}
    severity = score_grade(score)
    reasoning = _compute_reasoning(
        breakdown, mode, recency_signal, threshold_low, threshold_high
    )
    if severity in ("critical", "high"):
        reasoning.insert(0, f"Severity: {severity}（{score:.0f} 分），建议优先处理。")
    return ScoreResult(score, breakdown, reasoning, recency_signal, severity)


def _compute_reasoning(
    breakdown: dict[BreakdownKey, float],
    mode: ScoringMode,
    recency_signal: float,
    threshold_low: float,
    threshold_high: float,
) -> list[str]:
    """把数值分解翻译为可读理由。"""
    significant, dominant = 20.0, 30.0
    b = breakdown
    results: list[str] = []

    gini = b.get(BreakdownKey.GINI, 0.0)
    age = b.get(BreakdownKey.AGE, 0.0)
    low_recent = b.get(BreakdownKey.LOW_RECENT, 0.0)
    loc = b.get(BreakdownKey.LOC, 0.0)
    churn = b.get(BreakdownKey.CHURN, 0.0)
    inv_contrib = b.get(BreakdownKey.INV_CONTRIB, 0.0)

    if gini > significant and age > significant and low_recent > significant:
        results.append(
            "Institutional Amnesia: 关键逻辑集中在不活跃的作者手中，维护衰减风险高。"
        )
    if churn > dominant and loc > significant:
        results.append("Volatile Anchor: 大模块频繁大幅改动，重构回报高。")
    if gini > dominant or inv_contrib > dominant:
        results.append("Knowledge Silo: 文件所有权过度集中在少数人手中。")

    if len(results) < 2:
        if churn > significant:
            if recency_signal > threshold_high:
                msg = "High Churn: 近期波动表明该文件是当前开发瓶颈。"
            elif recency_signal < threshold_low:
                msg = "Historical Hotspot: 累计改动巨大，但近期已趋稳定。"
            else:
                msg = "High Churn: 高累计波动表明该文件是历史瓶颈。"
            results.append(msg)
        if low_recent > significant:
            results.append("Knowledge Decay: 文件久未更新，机构性遗忘风险上升。")
        if loc > significant:
            results.append("Structural Complexity: 高代码行数增加维护者的认知负担。")

    if mode == ScoringMode.ROI:
        if churn > significant and loc > significant:
            results.append("High Conflict Tax: 大文件上的并行开发带来协调开销。")
        if gini > significant:
            results.append("Knowledge Fragility: 主要所有者缺席时财务风险高。")

    if mode == ScoringMode.RISK and not results:
        results.append("Ownership Risk: 该资源贡献者多样性偏低。")

    return results


def score_file(metrics: FileMetrics, mode: ScoringMode, config) -> FileResult:
    """对单个文件评分：计算全部基础模式，再按活动模式决定 ``mode_score``。

    ``config`` 为 :class:`~githotmap.config.config.ScoringConfig`（或任何提供
    ``weights_for`` / ``recency_threshold_low`` / ``recency_threshold_high`` 的对象）。
    """
    result = FileResult(metrics=metrics)
    result.recency_threshold_low = config.recency_threshold_low
    result.recency_threshold_high = config.recency_threshold_high

    caps = getattr(config, "normalization_caps", None)
    for base in _BASE_MODES:
        sr = compute_score(
            metrics,
            base,
            config.weights_for(base),
            config.recency_threshold_low,
            config.recency_threshold_high,
            caps=caps,
        )
        result.scores[base.value] = sr.score
        result.breakdowns[base.value] = {k.value: v for k, v in sr.breakdown.items()}
        result.reasoning[base.value] = sr.reasoning
        result.severities[base.value] = sr.severity
        result.recency_signal = sr.recency_signal

    result.mode_score = result.scores.get(mode.value, 0.0)
    return result


def score_files(metrics_map, mode: ScoringMode, config) -> list[FileResult]:
    """批量评分，返回 FileResult 列表（未排序）。"""
    return [score_file(m, mode, config) for m in metrics_map]


def compute_composite_score(
    file_result: FileResult, composite: CompositeMode, blend: list[tuple[ScoringMode, float]]
) -> tuple[float, dict[str, float]]:
    """融合基础模式分数为复合分数，并返回融合后的分解。"""
    weights = _normalize_blend(blend)
    blended = 0.0
    blended_breakdown: dict[str, float] = {}
    for base, weight in weights.items():
        score = file_result.scores.get(base.value)
        if score is None:
            continue
        blended += score * weight
        for key, value in file_result.breakdowns.get(base.value, {}).items():
            blended_breakdown[key] = blended_breakdown.get(key, 0.0) + value * weight
    return clamp(blended, 0.0, 100.0), blended_breakdown


def _normalize_blend(blend: list[tuple[ScoringMode, float]]) -> dict[ScoringMode, float]:
    """归一化配比权重；非法/不完整时回退为等权。"""
    weights: dict[ScoringMode, float] = {}
    total = 0.0
    for mode, w in blend:
        if w <= 0:
            return {m: 1.0 / len(blend) for m, _ in blend}
        weights[mode] = w
        total += w
    if total <= 0:
        return {m: 1.0 / len(blend) for m, _ in blend}
    return {m: w / total for m, w in weights.items()}


def _composite_reasoning(
    file_result: FileResult, composite: CompositeMode, blend: list[tuple[ScoringMode, float]]
) -> list[str]:
    """为复合模式生成理由：标注配比，并汇总各组成基础模式的理由。

    理由按组成模式的权重从高到低拼接；模式名以 ``hot``/``risk`` 等原文呈现，
    便于与渲染层的模式切换器对应。若无任何组成模式产出理由，则回退为一条
    总体说明，保证渲染层始终有内容可显示。
    """
    weights = _normalize_blend(blend)
    header = "Composite Score: " + " + ".join(
        f"{base.value} {weight:.0%}" for base, weight in weights.items()
    )
    reasons: list[str] = [header]
    for base, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True):
        if weight <= 0:
            continue
        for reason in file_result.reasoning.get(base.value, []):
            reasons.append(f"[{base.value}] {reason}")
    if len(reasons) == 1:
        reasons.append(f"复合模式 {composite.value} 的各组成信号均未超过显著性阈值。")
    return reasons


def apply_composite(file_result: FileResult, composite: CompositeMode, blend) -> None:
    """把复合分数写回 ``file_result``（以复合模式名为键），并设为当前排序分数。

    同时写入融合后的分解与理由，保证复合模式与基础模式在渲染层有完整对称的输出。
    """
    score, breakdown = compute_composite_score(file_result, composite, blend)
    file_result.scores[composite.value] = score
    file_result.breakdowns[composite.value] = breakdown
    file_result.reasoning[composite.value] = _composite_reasoning(file_result, composite, blend)
    file_result.severities[composite.value] = score_grade(score)
    file_result.mode_score = score
