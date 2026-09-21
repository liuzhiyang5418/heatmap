"""领域模型：评分模式、指标与结果数据类。

本模块是包内其它模块共享的"契约层"，只依赖标准库，不引入任何上层依赖，
从而保证 ``core`` 与 ``renderers`` 之间单向、无环的引用关系。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class ScoringMode(str, Enum):
    """四种基础评分模式，语义与参考工具 hotspot 对齐。"""

    HOT = "hot"
    RISK = "risk"
    COMPLEXITY = "complexity"
    ROI = "roi"


class CompositeMode(str, Enum):
    """复合评分模式：融合两种基础模式以暴露多维风险。"""

    ACTIVE_OWNERS = "active_owners"  # hot 50% + risk 50%
    REFACTOR_NOW = "refactor_now"  # complexity 60% + roi 40%
    LEGACY_DEBT = "legacy_debt"  # complexity 70% + risk 30%


class BreakdownKey(str, Enum):
    """评分分解（breakdown）中的归一化信号键。"""

    AGE = "age"
    CHURN = "churn"
    COMMITS = "commits"
    CONTRIB = "contrib"
    SIZE = "size"
    GINI = "gini"
    INV_CONTRIB = "inv_contrib"
    LOC = "loc"
    LOW_RECENT = "low_recent"


@dataclass(slots=True)
class FileMetrics:
    """单个文件聚合出的原始指标（未评分）。"""

    path: str
    size_bytes: int = 0
    lines_of_code: float = 0.0
    commits: float = 0.0
    churn: float = 0.0  # 累计新增 + 删除行数
    recent_commits: float = 0.0
    recent_churn: float = 0.0
    unique_contributors: float = 0.0
    age_days: float = 0.0
    gini: float = 0.0  # 贡献者集中度 [0,1]
    decayed_commits: float = 0.0
    decayed_churn: float = 0.0
    # 每位贡献者的提交次数，用于事后复算 Gini / 调试。
    contributor_commits: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "lines_of_code": self.lines_of_code,
            "commits": self.commits,
            "churn": self.churn,
            "recent_commits": self.recent_commits,
            "recent_churn": self.recent_churn,
            "unique_contributors": self.unique_contributors,
            "age_days": self.age_days,
            "gini": self.gini,
            "decayed_commits": self.decayed_commits,
            "decayed_churn": self.decayed_churn,
        }


@dataclass(slots=True)
class FileResult:
    """一个文件经评分后的完整结果，可直接序列化供渲染层消费。"""

    metrics: FileMetrics
    recency_signal: float = 0.0
    recency_threshold_low: float = 0.5
    recency_threshold_high: float = 0.7
    # mode 名称(str) -> 0–100 分
    scores: dict[str, float] = field(default_factory=dict)
    # mode 名称(str) -> {BreakdownKey.value(str): 百分比贡献}
    breakdowns: dict[str, dict[str, float]] = field(default_factory=dict)
    # mode 名称(str) -> 自然语言理由列表
    reasoning: dict[str, list[str]] = field(default_factory=dict)
    # mode 名称(str) -> 风险等级（critical/high/medium/low）
    severities: dict[str, str] = field(default_factory=dict)
    # 当前活动评分模式的分数（排序依据）。
    mode_score: float = 0.0

    # ---- 便捷透传属性，避免调用方反复访问 metrics ----
    @property
    def path(self) -> str:
        return self.metrics.path

    @property
    def size_bytes(self) -> int:
        return self.metrics.size_bytes

    @property
    def lines_of_code(self) -> float:
        return self.metrics.lines_of_code

    @property
    def commits(self) -> float:
        return self.metrics.commits

    @property
    def churn(self) -> float:
        return self.metrics.churn

    @property
    def unique_contributors(self) -> float:
        return self.metrics.unique_contributors

    @property
    def gini(self) -> float:
        return self.metrics.gini

    @property
    def age_days(self) -> float:
        return self.metrics.age_days

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "metrics": self.metrics.to_dict(),
            "recency_signal": self.recency_signal,
            "recency_threshold_low": self.recency_threshold_low,
            "recency_threshold_high": self.recency_threshold_high,
            "scores": self.scores,
            "breakdowns": self.breakdowns,
            "reasoning": self.reasoning,
            "severities": self.severities,
            "mode_score": self.mode_score,
        }


@dataclass(slots=True)
class FolderResult:
    """目录级聚合结果（按文件结果上卷求和）。"""

    path: str
    score: float = 0.0
    file_count: int = 0
    total_commits: float = 0.0
    total_churn: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "score": self.score,
            "file_count": self.file_count,
            "total_commits": self.total_commits,
            "total_churn": self.total_churn,
        }


@dataclass(slots=True)
class AnalysisResult:
    """一次完整分析的产出，是核心引擎与渲染层之间的唯一数据契约。"""

    repo_path: str
    repo_urn: str
    mode: str
    files: list[FileResult] = field(default_factory=list)
    folders: list[FolderResult] = field(default_factory=list)
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "repo_urn": self.repo_urn,
            "mode": self.mode,
            "analyzed_at": self.analyzed_at,
            "files": [f.to_dict() for f in self.files],
            "folders": [f.to_dict() for f in self.folders],
        }
