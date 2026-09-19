"""文件发现层：按后缀与排除规则对仓库工作区做确定性遍历。

设计要点：

- **目录剪枝优先**：在 ``os.walk`` 中原地修改 ``dirnames`` 跳过 ``.git``/``__pycache__``
  等目录，避免「先全量收集再逐个过滤」造成的重复 I/O（性能非功能需求的落点）；
- **确定性**：目录名与文件名均排序后处理，结果再按路径升序排列，保证同样输入逐字节同输出；
- **不跟随符号链接**（默认）：符号链接**文件**仍作为候选产出（由上层标记 ``symlink``
  限制码，保证可审计），符号链接**目录**直接剪枝以避免环路与重复计数。
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

#: 默认排除规则。以 ``/`` 结尾表示「目录名」，命中路径中任一层级即生效。
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/",
    "__pycache__/",
    ".venv/",
    "venv/",
    "env/",
    ".tox/",
    ".nox/",
    ".eggs/",
    "*.egg-info/",
    "build/",
    "dist/",
    "site-packages/",
    "node_modules/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".ipynb_checkpoints/",
    ".idea/",
    ".vscode/",
)


def is_excluded(rel_path: str, patterns: Iterable[str]) -> bool:
    """判断（仓库根相对的 POSIX）路径是否命中排除规则。

    - 以 ``/`` 结尾的模式按**目录名**处理：路径中任一层级与之 ``fnmatch`` 匹配即命中，
      因此 ``*.egg-info/`` 能命中 ``src/githotmap.egg-info/PKG-INFO``；
    - 其余模式对**整条路径**做 ``fnmatch`` 匹配，``*`` 可跨越 ``/``；
    - 空串模式忽略。
    """
    parts: list[str] | None = None
    for raw in patterns:
        pattern = raw.strip()
        if not pattern:
            continue
        if pattern.endswith("/"):
            segment = pattern[:-1]
            if not segment:
                continue
            if parts is None:
                parts = rel_path.split("/")
            if any(fnmatch.fnmatch(part, segment) for part in parts):
                return True
            continue
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def find_repository_root(path: str | Path) -> Path | None:
    """向上查找 Git 工作区根（含 ``.git`` 的目录），找不到返回 ``None``。

    兼容 ``.git`` 为**文件**的情形（git worktree 与 submodule 都是这样），
    因此这里用 ``exists()`` 而非 ``is_dir()``。
    """
    try:
        current = Path(path).resolve()
    except OSError:
        return None
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


@dataclass(slots=True)
class WalkEntry:
    """一个候选文件：仓库根相对 POSIX 路径 + 绝对路径。"""

    path: str
    absolute: Path
    is_symlink: bool = False


@dataclass(slots=True)
class WalkResult:
    """一次目录遍历的产出。"""

    root: Path
    entries: list[WalkEntry] = field(default_factory=list)
    excluded_dirs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files_seen: int = 0
    files_excluded: int = 0


def _rel_posix(base: Path, target: Path) -> str | None:
    """把 ``target`` 表示为相对 ``base`` 的 POSIX 路径；不在其下则返回 ``None``。"""
    try:
        return target.relative_to(base).as_posix()
    except ValueError:
        return None


def walk_candidates(
    scan_root: str | Path,
    path_base: str | Path,
    include_suffixes: Iterable[str] = (".py",),
    exclude_patterns: Iterable[str] = (),
    follow_symlinks: bool = False,
) -> WalkResult:
    """确定性遍历 ``scan_root``，返回命中后缀且未被排除的候选文件。

    :param scan_root: 实际遍历的根目录。
    :param path_base: 生成相对路径的基准目录（通常是 Git 工作区根）。
    :param include_suffixes: 参与扫描的后缀，大小写不敏感。
    :param exclude_patterns: 排除规则，语义见 :func:`is_excluded`。
    :param follow_symlinks: 是否读取符号链接指向的真实内容。
    """
    root = Path(scan_root).resolve()
    base = Path(path_base).resolve()
    suffixes = tuple(s.lower() for s in include_suffixes)
    patterns = [p for p in exclude_patterns if p and p.strip()]
    result = WalkResult(root=root)

    def on_error(exc: OSError) -> None:
        # 单个目录读不动不应中断整次扫描。
        result.errors.append(str(exc))

    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=follow_symlinks, onerror=on_error
    ):
        current = Path(dirpath)

        # ---- 目录剪枝：原地改写 dirnames，被剔除的子树不会被 descend ----
        kept: list[str] = []
        for name in sorted(dirnames):
            child = current / name
            rel = _rel_posix(base, child)
            if rel is None:
                continue
            if is_excluded(rel, patterns):
                result.excluded_dirs.append(f"{rel}/")
                continue
            if not follow_symlinks and child.is_symlink():
                result.excluded_dirs.append(f"{rel}/")
                continue
            kept.append(name)
        dirnames[:] = kept

        # ---- 文件筛选 ----
        for name in sorted(filenames):
            result.files_seen += 1
            if not name.lower().endswith(suffixes):
                continue
            child = current / name
            rel = _rel_posix(base, child)
            if rel is None:
                continue
            if is_excluded(rel, patterns):
                result.files_excluded += 1
                continue
            is_link = child.is_symlink()
            if is_link and not follow_symlinks:
                # 仍作为候选产出，交由上层记录 symlink 限制码，保证覆盖率可审计。
                result.entries.append(WalkEntry(path=rel, absolute=child, is_symlink=True))
                continue
            result.entries.append(WalkEntry(path=rel, absolute=child))

    result.entries.sort(key=lambda entry: entry.path)
    result.excluded_dirs.sort()
    result.errors.sort()
    return result
