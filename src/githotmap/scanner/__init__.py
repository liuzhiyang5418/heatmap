"""Repository Scanner（仓库扫描器）—— Member 2 负责的模块。

职责：扫描仓库**工作区**，产出静态结构事实。

- 文件发现：按后缀与排除规则做确定性遍历（目录剪枝优先）；
- 结构解析：标准库 ``ast`` 提取类/函数/方法符号、导入、圈复杂度近似、嵌套深度；
- 规模度量：字节数、代码/注释/文档字符串/空行构成、内容 SHA-256；
- 可审计性：记录被排除的目录与每个文件的解析限制码。

对外契约见 ``docs/scanner-interface.md``。典型用法::

    from githotmap.scanner import scan_repository

    scan = scan_repository(".")
    scan.paths()        # 全部 Python 文件（仓库根相对 POSIX 路径，已排序）
    scan.by_path()      # {path: FileStructure}，供 M4/M5 做字典 join
    scan.to_dict()      # 已是 JSON 原生类型，M6 可直接 json.dumps

**边界**：本模块不读取 Git 历史（M4）、不提取 TODO/FIXME（M3）、不计算技术债分数（M5）、
不做任何展示（M6）。
"""

from __future__ import annotations

from githotmap.scanner.models import (
    FileStructure,
    Limitation,
    LineCounts,
    RepositoryScan,
    ScanStats,
    SymbolInfo,
    SymbolKind,
)
from githotmap.scanner.parser import (
    ParsedSource,
    classify_lines,
    count_lines_plain,
    docstring_rows,
    extract_imports,
    extract_symbols,
    parse_python_source,
)
from githotmap.scanner.scanner import (
    RepositoryScanner,
    ScanConfig,
    ScanError,
    scan_repository,
)
from githotmap.scanner.walker import (
    DEFAULT_EXCLUDES,
    WalkEntry,
    WalkResult,
    find_repository_root,
    is_excluded,
    walk_candidates,
)

__all__ = [
    "DEFAULT_EXCLUDES",
    "FileStructure",
    "Limitation",
    "LineCounts",
    "ParsedSource",
    "RepositoryScan",
    "RepositoryScanner",
    "ScanConfig",
    "ScanError",
    "ScanStats",
    "SymbolInfo",
    "SymbolKind",
    "WalkEntry",
    "WalkResult",
    "classify_lines",
    "count_lines_plain",
    "docstring_rows",
    "extract_imports",
    "extract_symbols",
    "find_repository_root",
    "is_excluded",
    "parse_python_source",
    "scan_repository",
    "walk_candidates",
]
