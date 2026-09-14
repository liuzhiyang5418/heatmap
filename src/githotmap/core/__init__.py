"""核心引擎包：领域模型、采集、指标、评分、排序与流水线。"""

from __future__ import annotations

from githotmap.core import git, metrics, ranking, scoring
from githotmap.core.models import (
    AnalysisResult,
    BreakdownKey,
    CompositeMode,
    FileMetrics,
    FileResult,
    FolderResult,
    ScoringMode,
)
from githotmap.core.pipeline import AnalysisPipeline

__all__ = [
    "AnalysisPipeline",
    "AnalysisResult",
    "BreakdownKey",
    "CompositeMode",
    "FileMetrics",
    "FileResult",
    "FolderResult",
    "ScoringMode",
    "git",
    "metrics",
    "ranking",
    "scoring",
]
