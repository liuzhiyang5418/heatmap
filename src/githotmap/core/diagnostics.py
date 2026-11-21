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


#: 每个原因码对应「读者接下来该做什么」。
#: 把可审计性从「知道为什么失败」推进到「知道怎么处置」，这是 Sprint 3 的
#: 调试与维护支持要求。原则：只写**可执行**的动作或明确的「无需处理」，
#: 不写「请检查一下」这类空话。
REMEDIATION_HINTS: dict[DegradationCode, str] = {
    DegradationCode.SYMLINK: (
        "符号链接默认不跟随。确需分析其目标时，把目标文件移入仓库或用真实路径引用。"
    ),
    DegradationCode.NOT_TEXT: (
        "文件被判为二进制。若属生成物，用 --exclude 跳过（如 --exclude '**/dist/')。"
    ),
    DegradationCode.TOO_LARGE: (
        "文件超过 2 MB 的解析上限。大文件本身可作为拆分信号；不关心时用 --exclude 跳过。"
    ),
    DegradationCode.UNREADABLE: (
        "读取失败（权限或文件被占用）。检查权限，或先关闭占用该文件的进程再扫描。"
    ),
    DegradationCode.UNSUPPORTED_LANGUAGE: (
        "该后缀不做结构解析，只统计规模。需要覆盖时在 ScanConfig.include_suffixes 登记"
        "并补对应解析器。"
    ),
    DegradationCode.SYNTAX_ERROR: (
        "Python 语法错误导致结构信号缺失。先修复语法；若该文件本不该进仓库，用 --exclude 排除。"
    ),
    DegradationCode.GIT_QUOTEPATH: (
        "git 输出了转义路径，会与文件系统路径对不上。确认调用 git 时已关闭 core.quotepath。"
    ),
    DegradationCode.STAGE_FAILED: (
        "整个阶段失败，后续统计可能不可用。查看 detail 中的异常，多为路径、权限或 git 环境问题。"
    ),
    DegradationCode.REPO_NOT_GIT: (
        "目标目录不是 Git 仓库，历史类指标不可用。请指向仓库根目录，或先 git init。"
    ),
    DegradationCode.EMPTY_REPO: (
        "仓库尚无提交，历史指标为空属正常。至少产生一次提交后重跑。"
    ),
    DegradationCode.SHALLOW_CLONE: (
        "浅克隆缺少父提交，边界提交的改动量无法计算。需要完整历史时执行 git fetch --unshallow。"
    ),
}

_FALLBACK_HINT = "该原因码未登记处置建议；请参考 docs/nfr.md §2.3 的决策说明。"


def remediation_hint(code: DegradationCode | str) -> str:
    """返回原因码的处置建议；未知码回退到通用提示，不抛异常。"""
    try:
        parsed = code if isinstance(code, DegradationCode) else DegradationCode(code)
    except ValueError:
        return _FALLBACK_HINT
    return REMEDIATION_HINTS.get(parsed, _FALLBACK_HINT)


__all__ = [
    "REMEDIATION_HINTS",
    "AnalysisDegradedError",
    "AnalysisStats",
    "Degradation",
    "DegradationCode",
    "remediation_hint",
]

