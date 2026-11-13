"""可审计诊断模型：统一记录分析阶段的降级原因与覆盖统计。

依赖方向是**单向**的，改动前请先确认没有破坏它：

- 只依赖标准库 + ``githotmap.scanner``（复用原因码的唯一来源，见 NFR-2 契约）；
- 尤其**不得**导入 ``githotmap.config``，避免重新引入 config 与 core 之间的循环依赖；
- 反过来 ``scanner`` 也不得导入本模块，否则成环。依赖方向固定为 ``core → scanner``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from githotmap.scanner import Limitation


class DegradationCode(str, Enum):
    """所有分析阶段共享的机器可读降级原因码。

    前 6 个取值**直接引用** :class:`githotmap.scanner.Limitation`（NFR-2 的唯一来源），
    不复制字面量：任何一方的改动都会立即反映到另一方，从根上消除「两处各自漂移」
    （这正是 M4-2 的 ``core.quotepath`` 那类静默失配）。其余为其它阶段的扩展码。
    """

    # 扫描阶段：唯一来源是 scanner.Limitation（见 docs/scanner-interface.md §4.5）
    SYMLINK = Limitation.SYMLINK.value
    NOT_TEXT = Limitation.NOT_TEXT.value
    TOO_LARGE = Limitation.TOO_LARGE.value
    UNREADABLE = Limitation.UNREADABLE.value
    UNSUPPORTED_LANGUAGE = Limitation.UNSUPPORTED_LANGUAGE.value
    SYNTAX_ERROR = Limitation.SYNTAX_ERROR.value
    # 其它阶段：由 core 侧扩展，不进入 scanner 的语义范围
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

