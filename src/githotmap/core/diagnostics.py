"""可审计诊断模型：统一记录分析阶段的降级原因与覆盖统计。

本模块是核心契约层，只依赖标准库；尤其不得导入 ``githotmap.config``，
避免重新引入 config 与 core 之间的循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DegradationCode(str, Enum):
    """所有分析阶段共享的机器可读降级原因码。"""

    SYMLINK = "symlink"
    NOT_TEXT = "not-text"
    TOO_LARGE = "too-large"
    UNREADABLE = "unreadable"
    UNSUPPORTED_LANGUAGE = "unsupported-language"
    SYNTAX_ERROR = "syntax-error"
    GIT_QUOTEPATH = "git-quotepath"
    STAGE_FAILED = "stage-failed"
    REPO_NOT_GIT = "repo-not-git"
    EMPTY_REPO = "empty-repo"
    SHALLOW_CLONE = "shallow-clone"


@dataclass(slots=True)
class Degradation:
    """一次可恢复降级；summary 面向人，code 面向自动化处理。"""

    stage: str
    code: DegradationCode
    path: str | None
    summary: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为只含 JSON 原生类型的字典。"""
        return {
            "stage": self.stage,
            "code": self.code.value,
            "path": self.path,
            "summary": self.summary,
            "detail": self.detail,
        }


@dataclass(slots=True)
class AnalysisStats:
    """一次分析的覆盖率、阶段耗时与完整降级清单。"""

    files_matched: int = 0
    files_emitted: int = 0
    files_degraded: int = 0
    commits_seen: int = 0
    stage_elapsed_ms: dict[str, float] = field(default_factory=dict)
    degradations_by_code: dict[str, int] = field(default_factory=dict)
    degradations: list[Degradation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为只含 JSON 原生类型的字典，供渲染器与 CLI 消费。"""
        return {
            "files_matched": self.files_matched,
            "files_emitted": self.files_emitted,
            "files_degraded": self.files_degraded,
            "commits_seen": self.commits_seen,
            "stage_elapsed_ms": dict(self.stage_elapsed_ms),
            "degradations_by_code": dict(self.degradations_by_code),
            "degradations": [item.to_dict() for item in self.degradations],
        }


class AnalysisDegradedError(Exception):
    """当开启严格模式且发生降级时抛出，携带完整的降级信息。"""

    def __init__(self, stats: AnalysisStats):
        self.stats = stats
        codes = ", ".join(stats.degradations_by_code.keys())
        super().__init__(f"Analysis degraded in strict mode. Reasons: {codes}")


__all__ = ["AnalysisDegradedError", "AnalysisStats", "Degradation", "DegradationCode"]

