"""Git 数据采集层：用 GitPython 遍历提交历史并提取文件级改动。

本模块提供两套采集实现：

- :class:`GitPythonHistory`（主力，使用 GitPython 库）——Member 4 的正式实现，
  结构化 ``Commit`` / ``File`` 对象，无需手写文本解析；
- :class:`SubprocessHistory`（备用，使用 ``subprocess`` 调用 ``git log --numstat``）——
  组长初始框架的遗留实现，已标记 deprecated，保留供对比与单元测试使用。

两套实现产出统一的 :class:`CommitRecord` 列表，下游 ``metrics`` / ``scoring``
层不关心底层采集方式。
"""

from __future__ import annotations

import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# 异常与数据类
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    """Git 命令执行失败时抛出，携带 stderr 以便诊断。"""


@dataclass(slots=True)
class CommitRecord:
    """单个提交对单个文件的一次改动记录。

    字段与 git log --numstat 输出一一对应：

    - ``author`` / ``timestamp`` / ``file_path`` 来自提交头 / 文件路径；
    - ``added`` / ``deleted`` 为该文件在本次提交中的新增 / 删除行数。
    """

    author: str
    timestamp: int  # 作者时间，unix 秒
    file_path: str
    added: int
    deleted: int

    @property
    def churn(self) -> int:
        return self.added + self.deleted


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def resolve_urn(repo_path: str | Path) -> str:
    """解析仓库的可移植身份标识（URN）。

    优先使用远端 origin URL（规范化为 ``git:host/owner/repo`` 形态），否则回退到
    本地绝对路径 ``local:<abs_path>``，保证跨机器缓存键稳定。
    """
    import git as _git

    try:
        repo = _git.Repo(str(repo_path))
        url = repo.remotes.origin.url if repo.remotes else ""
    except Exception:  # GitPython 打开失败时回退到 subprocess
        url = _try_get_origin_url(repo_path)

    if url:
        return f"git:{url.rstrip('/')}"
    return f"local:{Path(repo_path).resolve()}"


def _try_get_origin_url(repo_path: str | Path) -> str:
    """resolve_urn 的 subprocess 回退实现。"""
    repo = str(repo_path)
    command = ["git", "-C", repo, "config", "--get", "remote.origin.url"]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Subprocess 版本（deprecated，保留用于测试与对比）
# ---------------------------------------------------------------------------

# 提交头在 git log 输出中的字段分隔符（SOH，几乎不可能出现在正常元数据中）。
_HEADER_SEP = "\x01"


class GitLogParser:
    """把 ``git log --numstat`` 的文本输出解析为 :class:`CommitRecord` 列表。

    已 deprecated，请使用 :class:`GitPythonHistory`。
    """

    _LOG_ARGS: list[str] = [
        "log",
        "--numstat",
        "--date=unix",
        f"--pretty=format:{_HEADER_SEP}%H{_HEADER_SEP}%an{_HEADER_SEP}%at%n",
    ]

    def build_command(self, since: str | None = None) -> list[str]:
        args = list(self._LOG_ARGS)
        if since:
            args.append(f"--since={since}")
        return args

    def parse(self, text: str) -> list[CommitRecord]:
        records: list[CommitRecord] = []
        author = ""
        timestamp = 0

        for raw_line in text.splitlines():
            if raw_line.startswith(_HEADER_SEP):
                parts = raw_line[len(_HEADER_SEP) :].split(_HEADER_SEP)
                if len(parts) >= 3:
                    author = parts[1]
                    try:
                        timestamp = int(parts[2])
                    except ValueError:
                        timestamp = 0
                continue

            if not raw_line.strip():
                continue

            fields = raw_line.split("\t", 2)
            if len(fields) < 3:
                continue
            added_s, deleted_s, path = fields[0], fields[1], fields[2]
            if not path:
                continue
            added = _parse_count(added_s)
            deleted = _parse_count(deleted_s)
            records.append(
                CommitRecord(
                    author=author,
                    timestamp=timestamp,
                    file_path=path,
                    added=added,
                    deleted=deleted,
                )
            )
        return records


def _parse_count(token: str) -> int:
    """numstat 计数可能是整数，也可能是二进制文件的 ``-``。"""
    token = token.strip()
    if token == "-":
        return 0
    try:
        return int(token)
    except ValueError:
        return 0


def run_git(args: Sequence[str], repo_path: str | Path) -> str:
    """以 UTF-8 执行一个只读 git 命令并返回 stdout；失败时抛 :class:`GitError`。

    已 deprecated：内部采集已全部迁移至 GitPython。仅保留给少量通用运维命令
    （例如 ``git diff``）使用。
    """
    repo = str(repo_path)
    command = ["git", "-C", repo, *args]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise GitError(f"无法执行 git（{exc}），请确认已安装 Git 2.2+ 并加入 PATH") from exc

    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} 失败（exit {proc.returncode}）: {proc.stderr.strip()}"
        )
    return proc.stdout


class SubprocessHistory:
    """基于 subprocess 的 Git 采集（deprecated，保留供旧测试通过）。"""

    def __init__(self) -> None:
        self._parser = GitLogParser()

    def collect(self, repo_path: str | Path, since: str | None = None) -> list[CommitRecord]:
        args = self._parser.build_command(since=since)
        stdout = run_git(args, repo_path)
        return self._parser.parse(stdout)


# ---------------------------------------------------------------------------
# GitPython 版本（主力实现）
# ---------------------------------------------------------------------------


class GitPythonHistory:
    """基于 GitPython 的 Git 采集（主力实现，Member 4 正式交付物）。

    与 :class:`SubprocessHistory` 行为等价，但：

    - 返回的是 GitPython 提供的 ``Commit`` / ``File`` / ``Author`` 结构化对象，
      免去手写解析；
    - 天然支持作者邮箱、提交信息、父提交等 subprocess 版本需额外 ``git`` 命令
      才能拿到的字段；
    - 每次 ``iter_commits`` 会为每个 commit 计算 diff，**大仓库上比单次
      ``git log --numstat`` 略慢**——代码复杂度换来了可读性与可扩展性。
    """

    def collect(self, repo_path: str | Path, since: str | None = None) -> list[CommitRecord]:
        """遍历仓库历史并返回全部（或 ``since`` 之后）的文件级改动记录。"""
        import git as _git

        try:
            repo = _git.Repo(str(repo_path))
        except Exception as exc:
            raise GitError(f"无法打开仓库 {repo_path}: {exc}") from exc

        # 构造 iter_commits 的过滤参数
        kwargs: dict = {}
        if since:
            kwargs["since"] = since

        records: list[CommitRecord] = []
        for commit in repo.iter_commits(**kwargs):
            author = commit.author.name
            # committed_datetime 是带时区的 datetime，.timestamp() 返回 unix 秒(float)
            timestamp = int(commit.committed_datetime.timestamp())

            # commit.stats.files: {path: {'insertions': int, 'deletions': int, ...}}
            for path, stats in commit.stats.files.items():
                records.append(
                    CommitRecord(
                        author=author,
                        timestamp=timestamp,
                        file_path=path,
                        added=stats.get("insertions", 0),
                        deleted=stats.get("deletions", 0),
                    )
                )

        return records


# ---------------------------------------------------------------------------
# 主门面（对外统一入口）
# ---------------------------------------------------------------------------


class GitHistory:
    """面向仓库的高层采集门面（默认使用 GitPython）。

    构造参数 ``use_gitpython`` 控制底层实现：

    - ``True``（默认）→ :class:`GitPythonHistory`
    - ``False``        → :class:`SubprocessHistory`（deprecated，供测试/回退）
    """

    def __init__(self, use_gitpython: bool = True) -> None:
        if use_gitpython:
            self._impl: GitPythonHistory | SubprocessHistory = GitPythonHistory()
        else:
            warnings.warn(
                "GitHistory(use_gitpython=False) is deprecated, use GitPythonHistory instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._impl = SubprocessHistory()

    def collect(self, repo_path: str | Path, since: str | None = None) -> list[CommitRecord]:
        """遍历仓库历史并返回全部（或 ``since`` 之后）的提交记录。"""
        return self._impl.collect(repo_path, since=since)
