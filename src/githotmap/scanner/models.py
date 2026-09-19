"""Repository Scanner 的领域模型（契约层）。

本模块定义仓库扫描器对外暴露的**全部**数据结构，是 M2 与下游模块（M3 TODO 检测、
M4 Git 历史分析、M5 评分引擎、M6 Flask 看板）之间的唯一数据契约。

设计约束（与 ``core/models.py`` 保持一致）：

- 只依赖标准库，不反向依赖任何上层模块；
- 每个模型均为 ``dataclass(slots=True)`` 且实现 ``to_dict()``，返回值只含 JSON
  原生类型，M6 可直接 ``json.dumps``；
- 枚举以 ``str`` 值出现在数据结构字段中（边界用字符串、内部用枚举），
  与 ``core/models.py`` 中 ``AnalysisResult.mode`` 的既有约定一致。

路径规范【契约】：所有对外路径均为「Git 工作区根相对 + POSIX 正斜杠」，
不带 ``./`` 前缀。详见 ``docs/scanner-interface.md`` §4.1。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SymbolKind(str, Enum):
    """代码结构解析出的符号类型。"""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class Limitation(str, Enum):
    """文件结构未能完整解析的原因码（用于审计扫描覆盖率）。"""

    SYMLINK = "symlink"
    NOT_TEXT = "not-text"
    TOO_LARGE = "too-large"
    UNREADABLE = "unreadable"
    UNSUPPORTED_LANGUAGE = "unsupported-language"
    SYNTAX_ERROR = "syntax-error"


@dataclass(slots=True)
class LineCounts:
    """一个文件的行数构成。

    不变量【契约】：``total == code + comment + docstring + blank``。
    既含代码又含行尾注释的行计入 ``code``（不重复计数）；多行字符串的内容行计入
    ``code``；文档字符串覆盖的行（含其中的空行）全部计入 ``docstring``。
    """

    total: int = 0
    code: int = 0
    comment: int = 0
    docstring: int = 0
    blank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "code": self.code,
            "comment": self.comment,
            "docstring": self.docstring,
            "blank": self.blank,
        }


@dataclass(slots=True)
class SymbolInfo:
    """代码结构解析出的单个符号（类 / 函数 / 方法）。

    ``branch_count`` 的口径见 ``docs/scanner-interface.md`` §5.2：只统计**函数体内部**
    的分支点，且不递归进入嵌套的 ``def``/``async def``/``lambda``/``class``。
    对 ``kind == "class"`` 的符号，``branch_count`` 与 ``nesting_depth`` 恒为 0
    （复杂度归属到具体函数/方法）。
    """

    name: str
    qualname: str
    kind: str = SymbolKind.FUNCTION.value
    parent: str | None = None
    lineno: int = 0
    end_lineno: int = 0
    decorators: list[str] = field(default_factory=list)
    has_docstring: bool = False
    is_public: bool = True
    params: int = 0
    branch_count: int = 0
    nesting_depth: int = 0

    @property
    def body_lines(self) -> int:
        """符号跨越的行数（含 ``def``/``class`` 行与 ``end_lineno``）。"""
        if self.end_lineno < self.lineno:
            return 0
        return self.end_lineno - self.lineno + 1

    @property
    def cyclomatic_complexity(self) -> int:
        """圈复杂度的静态近似：``branch_count + 1``。"""
        return self.branch_count + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualname": self.qualname,
            "parent": self.parent,
            "kind": self.kind,
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "body_lines": self.body_lines,
            "decorators": list(self.decorators),
            "has_docstring": self.has_docstring,
            "is_public": self.is_public,
            "params": self.params,
            "branch_count": self.branch_count,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "nesting_depth": self.nesting_depth,
        }


@dataclass(slots=True)
class FileStructure:
    """单个文件的结构事实。

    每一个候选文件都会产出一个 :class:`FileStructure`（即使解析失败），
    以保证下游总能看到完整的文件清单——这对 M4 的路径对齐与 M6 的覆盖率展示都是必要的。
    """

    path: str
    size_bytes: int = 0
    lines: LineCounts = field(default_factory=LineCounts)
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    parse_error: str | None = None
    sha256: str | None = None
    parsed: bool = False

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    @property
    def class_count(self) -> int:
        return sum(1 for s in self.symbols if s.kind == SymbolKind.CLASS.value)

    @property
    def function_count(self) -> int:
        return sum(1 for s in self.symbols if s.kind != SymbolKind.CLASS.value)

    @property
    def max_cyclomatic_complexity(self) -> int:
        """文件内最大的圈复杂度（无符号时为 0）。"""
        if not self.symbols:
            return 0
        return max(s.cyclomatic_complexity for s in self.symbols)

    @property
    def max_nesting_depth(self) -> int:
        """文件内最大的嵌套深度（无符号时为 0）。"""
        if not self.symbols:
            return 0
        return max(s.nesting_depth for s in self.symbols)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "parsed": self.parsed,
            "parse_error": self.parse_error,
            "limitations": list(self.limitations),
            "imports": list(self.imports),
            "lines": self.lines.to_dict(),
            "symbols": [s.to_dict() for s in self.symbols],
        }


@dataclass(slots=True)
class ScanStats:
    """一次扫描的统计信息（用于覆盖率展示与性能评估）。

    不变量【契约】：``files_emitted == files_matched - files_excluded``。
    """

    files_seen: int = 0
    files_matched: int = 0
    files_excluded: int = 0
    files_emitted: int = 0
    files_parsed: int = 0
    files_with_limitations: int = 0
    excluded_dirs: list[str] = field(default_factory=list)
    total_bytes: int = 0
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_seen": self.files_seen,
            "files_matched": self.files_matched,
            "files_excluded": self.files_excluded,
            "files_emitted": self.files_emitted,
            "files_parsed": self.files_parsed,
            "files_with_limitations": self.files_with_limitations,
            "excluded_dirs": list(self.excluded_dirs),
            "total_bytes": self.total_bytes,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(slots=True)
class RepositoryScan:
    """一次仓库扫描的顶层产出。

    - ``root``：本次扫描的根目录（用户传入者）；
    - ``path_base``：:attr:`files` 中路径的基准目录（默认即 Git 工作区根，见 §4.1）；
    - ``scanned_at`` 与 ``stats.elapsed_ms`` 是仅有的两个**非确定性**字段。
    """

    root: str
    path_base: str
    files: list[FileStructure] = field(default_factory=list)
    stats: ScanStats = field(default_factory=ScanStats)
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def paths(self) -> list[str]:
        """全部文件路径（已排序），供 M3 遍历。"""
        return [f.path for f in self.files]

    def by_path(self) -> dict[str, FileStructure]:
        """路径到结构的索引，供 M4/M5 做字典 join。"""
        return {f.path: f for f in self.files}

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "path_base": self.path_base,
            "scanned_at": self.scanned_at,
            "stats": self.stats.to_dict(),
            "files": [f.to_dict() for f in self.files],
        }
