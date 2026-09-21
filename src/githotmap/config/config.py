"""配置层：评分权重、复合模式配比、仓库预设与运行时参数。

权重默认值与参考工具 hotspot 的 ``scoring_config.yaml`` 对齐，保证评分语义一致；
复合模式配比对齐其 ``active_owners / refactor_now / legacy_debt`` 三档。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from githotmap.core.metrics import DECAY_HALF_LIFE_DAYS, DEFAULT_RECENT_WINDOW_DAYS
from githotmap.core.models import BreakdownKey, CompositeMode, ScoringMode

# ---- 各基础评分模式的默认权重（缺失键按 0 处理）----
DEFAULT_WEIGHTS: dict[ScoringMode, dict[BreakdownKey, float]] = {
    ScoringMode.HOT: {
        BreakdownKey.COMMITS: 0.40,
        BreakdownKey.CHURN: 0.40,
        BreakdownKey.CONTRIB: 0.05,
        BreakdownKey.AGE: 0.10,
        BreakdownKey.SIZE: 0.05,
    },
    ScoringMode.RISK: {
        BreakdownKey.INV_CONTRIB: 0.25,
        BreakdownKey.GINI: 0.25,
        BreakdownKey.LOW_RECENT: 0.15,
        BreakdownKey.AGE: 0.15,
        BreakdownKey.SIZE: 0.10,
        BreakdownKey.LOC: 0.05,
        BreakdownKey.CHURN: 0.05,
    },
    ScoringMode.COMPLEXITY: {
        BreakdownKey.AGE: 0.30,
        BreakdownKey.LOC: 0.20,
        BreakdownKey.SIZE: 0.05,
        BreakdownKey.CHURN: 0.30,
        BreakdownKey.COMMITS: 0.10,
        BreakdownKey.LOW_RECENT: 0.05,
    },
    ScoringMode.ROI: {
        BreakdownKey.CHURN: 0.35,
        BreakdownKey.LOC: 0.25,
        BreakdownKey.GINI: 0.25,
        BreakdownKey.AGE: 0.15,
    },
}

# ---- 复合模式：base mode 列表 + 配比（运行时归一化）----
COMPOSITE_WEIGHTS: dict[CompositeMode, list[tuple[ScoringMode, float]]] = {
    CompositeMode.ACTIVE_OWNERS: [(ScoringMode.HOT, 0.5), (ScoringMode.RISK, 0.5)],
    CompositeMode.REFACTOR_NOW: [(ScoringMode.COMPLEXITY, 0.6), (ScoringMode.ROI, 0.4)],
    CompositeMode.LEGACY_DEBT: [(ScoringMode.COMPLEXITY, 0.7), (ScoringMode.RISK, 0.3)],
}

# ---- 仓库形状预设 ----
PRESETS: dict[str, dict] = {
    "small": {
        "mode": "hot",
        "limit": 10,
        "recency_threshold_low": 0.10,
        "recency_threshold_high": 0.40,
    },
    "large": {
        "mode": "roi",
        "limit": 30,
        "recency_threshold_low": 0.01,
        "recency_threshold_high": 0.05,
    },
    "infra": {
        "mode": "risk",
        "limit": 20,
        "recency_threshold_low": 0.05,
        "recency_threshold_high": 0.20,
    },
}


@dataclass(slots=True)
class ScoringConfig:
    """一次分析运行的运行时参数（评分 + 采集 + 输出）。"""

    mode: ScoringMode = ScoringMode.HOT
    limit: int = 20
    weights: dict[ScoringMode, dict[BreakdownKey, float]] = field(
        default_factory=lambda: dict(DEFAULT_WEIGHTS)
    )
    recency_threshold_low: float = 0.10
    recency_threshold_high: float = 0.40
    recent_window_days: float = DEFAULT_RECENT_WINDOW_DAYS
    decay_half_life_days: float = DECAY_HALF_LIFE_DAYS
    # 归一化上限覆盖（键见 scoring.DEFAULT_CAPS），用于按仓库规模调整饱和点。
    normalization_caps: dict[str, float] = field(default_factory=dict)
    exclude: list[str] = field(default_factory=list)
    since: str | None = None

    @classmethod
    def from_preset(cls, preset_name: str) -> "ScoringConfig":
        """依据仓库形状预设构造配置。"""
        preset = PRESETS.get(preset_name)
        if preset is None:
            raise KeyError(f"未知预设 {preset_name!r}，可选: {sorted(PRESETS)}")
        return cls(
            mode=ScoringMode(preset["mode"]),
            limit=preset["limit"],
            recency_threshold_low=preset["recency_threshold_low"],
            recency_threshold_high=preset["recency_threshold_high"],
        )

    def weights_for(self, mode: ScoringMode) -> dict[BreakdownKey, float]:
        return self.weights.get(mode, DEFAULT_WEIGHTS.get(mode, {}))
