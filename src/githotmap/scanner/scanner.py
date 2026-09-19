"""Repository Scanner 门面层：把「文件发现 → 读取 → 结构解析 → 统计」编排为一次扫描。

用法::

    from githotmap.scanner import scan_repository

    scan = scan_repository("/path/to/repo")
    for path in scan.paths():          # 已排序、已排除噪声
        ...
    payload = scan.to_dict()           # 已是 JSON 原生类型

契约与字段含义见 ``docs/scanner-interface.md``。
"""

from __future__ import annotations

import hashlib
import io
import time
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from githotmap.scanner.models import (
    FileStructure,
    Limitation,
    RepositoryScan,
    ScanStats,
)
from githotmap.scanner.parser import count_lines_plain, parse_python_source
from githotmap.scanner.walker import (
    DEFAULT_EXCLUDES,
    WalkEntry,
    find_repository_root,
    walk_candidates,
)

#: 能够进行 AST 结构解析的后缀（与「参与扫描的后缀」是两个概念）。
_PYTHON_SUFFIXES: tuple[str, ...] = (".py", ".pyw", ".pyi")


class ScanError(RuntimeError):
    """扫描前置条件不满足（根目录不存在或不是目录）时抛出。

    除此之外扫描过程**不抛异常**：单文件的权限、编码、语法问题一律降级为
    :class:`~githotmap.scanner.models.FileStructure` 上的 ``limitations``。
    """


@dataclass(slots=True)
class ScanConfig:
    """一次扫描的运行时参数（与仓库路径解耦，便于复用与单测注入）。"""

    #: 参与扫描的文件后缀，大小写不敏感。
    include_suffixes: tuple[str, ...] = (".py",)
    #: 在默认排除之外追加的排除规则，语义见 :func:`githotmap.scanner.walker.is_excluded`。
    exclude_patterns: list[str] = field(default_factory=list)
    #: 是否叠加 :data:`~githotmap.scanner.walker.DEFAULT_EXCLUDES`。
    use_default_excludes: bool = True
    #: 是否以 Git 工作区根作为路径基准（接口文档 §4.1 的强制契约）。
    respect_git_root: bool = True
    #: 是否读取符号链接指向的真实内容（默认否，避免环路与重复计数）。
    follow_symlinks: bool = False
    #: 超过该字节数的文件只统计规模，不做结构解析。
    max_file_bytes: int = 2_000_000
    #: 兜底解码方式（优先遵循 PEP 263 源码声明）。
    encoding: str = "utf-8"
    #: 关闭后只做文件发现与行数统计（快速模式）。
    parse_structure: bool = True
    #: 是否计算文件内容 SHA-256（用于增量扫描与评估契约冻结）。
    compute_hash: bool = True


def _decode(raw: bytes, fallback_encoding: str) -> str:
    """解码源码字节：优先遵循 PEP 263 的 ``coding`` 声明，失败则按兜底编码降级。"""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    except (SyntaxError, UnicodeDecodeError, LookupError):
        encoding = fallback_encoding
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


class RepositoryScanner:
    """仓库扫描器：文件发现与代码结构解析的单一入口。"""

    #: 组件唯一名称，便于日志与后续注册表查找。
    name: str = "repository-scanner"

    def __init__(self, config: ScanConfig | None = None) -> None:
        self.config = config or ScanConfig()

    # ---- 公共 API ----
    def scan(self, repo_path: str | Path) -> RepositoryScan:
        """扫描 ``repo_path`` 并返回 :class:`RepositoryScan`。

        :raises ScanError: ``repo_path`` 不存在或不是目录。
        """
        started = time.perf_counter()
        root = Path(repo_path)
        if not root.is_dir():
            raise ScanError(f"扫描根目录不存在或不是目录: {root}")
        root = root.resolve()
        base = self._path_base(root)

        walk = walk_candidates(
            scan_root=root,
            path_base=base,
            include_suffixes=self.config.include_suffixes,
            exclude_patterns=self._patterns(),
            follow_symlinks=self.config.follow_symlinks,
        )

        files = [self._build_file(entry) for entry in walk.entries]
        files.sort(key=lambda item: item.path)

        stats = ScanStats(
            files_seen=walk.files_seen,
            files_matched=len(walk.entries) + walk.files_excluded,
            files_excluded=walk.files_excluded,
            files_emitted=len(files),
            files_parsed=sum(1 for item in files if item.parsed),
            files_with_limitations=sum(1 for item in files if item.limitations),
            excluded_dirs=list(walk.excluded_dirs),
            total_bytes=sum(item.size_bytes for item in files),
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return RepositoryScan(
            root=str(root), path_base=str(base), files=files, stats=stats
        )

    # ---- 内部实现 ----
    def _patterns(self) -> list[str]:
        """默认排除 + 用户自定义排除。"""
        patterns: list[str] = []
        if self.config.use_default_excludes:
            patterns.extend(DEFAULT_EXCLUDES)
        patterns.extend(self.config.exclude_patterns)
        return patterns

    def _path_base(self, root: Path) -> Path:
        """解析路径基准目录（默认取 Git 工作区根）。"""
        if not self.config.respect_git_root:
            return root
        found = find_repository_root(root)
        return found if found is not None else root

    def _build_file(self, entry: WalkEntry) -> FileStructure:
        """读取单个候选文件并组装 :class:`FileStructure`。"""
        config = self.config
        item = FileStructure(path=entry.path)

        if entry.is_symlink:
            # 默认不跟随符号链接：只登记路径，不读内容。
            item.limitations.append(Limitation.SYMLINK.value)
            return item

        try:
            raw = entry.absolute.read_bytes()
        except OSError:
            item.limitations.append(Limitation.UNREADABLE.value)
            return item

        item.size_bytes = len(raw)
        if config.compute_hash:
            item.sha256 = hashlib.sha256(raw).hexdigest()

        if len(raw) > config.max_file_bytes:
            item.limitations.append(Limitation.TOO_LARGE.value)
            return item
        if b"\x00" in raw[:1024]:
            item.limitations.append(Limitation.NOT_TEXT.value)
            return item

        source = _decode(raw, config.encoding)
        is_python = entry.path.lower().endswith(_PYTHON_SUFFIXES)
        if not config.parse_structure or not is_python:
            if not is_python:
                item.limitations.append(Limitation.UNSUPPORTED_LANGUAGE.value)
            item.lines = count_lines_plain(source)
            return item

        parsed = parse_python_source(source)
        item.lines = parsed.lines
        item.symbols = parsed.symbols
        item.imports = parsed.imports
        item.parse_error = parsed.parse_error
        if parsed.parse_error is None:
            item.parsed = True
        else:
            item.limitations.append(Limitation.SYNTAX_ERROR.value)
        return item


def scan_repository(
    repo_path: str | Path,
    config: ScanConfig | None = None,
) -> RepositoryScan:
    """便捷函数：等价于 ``RepositoryScanner(config).scan(repo_path)``。"""
    return RepositoryScanner(config).scan(repo_path)
