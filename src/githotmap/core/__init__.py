"""核心引擎包：领域模型、采集、指标、评分与排序。

注意：``pipeline`` 是编排层，依赖 ``config`` 包，因此**不在本模块中 eager import**，
否则会与 ``config.config`` 形成循环。使用时请显式导入::

    from githotmap.core.pipeline import AnalysisPipeline
"""

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

__all__ = [
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
