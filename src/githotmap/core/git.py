"""Git 数据采集层：用 GitPython 遍历提交历史并提取文件级改动。

只做一次 ``iter_commits`` 遍历，同时拿到作者、时间与 per-file 的
added/deleted/churn，产出 :class:`CommitRecord` 列表供 ``metrics`` 层聚合。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import git as _git


# ---------------------------------------------------------------------------
# 异常与数据类
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    """Git 命令执行失败时抛出，携带 stderr 以便诊断。"""


@dataclass(slots=True)
class CommitRecord:
    """单个提交对单个文件的一次改动记录。"""

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
    try:
        repo = _git.Repo(str(repo_path))
        url = repo.remotes.origin.url if repo.remotes else ""
    except Exception:
        url = ""

    if url:
        return f"git:{url.rstrip('/')}"
    return f"local:{Path(repo_path).resolve()}"


# ---------------------------------------------------------------------------
# 采集门面
# ---------------------------------------------------------------------------


class GitHistory:
    """基于 GitPython 的 Git 采集门面。"""

    def collect(self, repo_path: str | Path, since: str | None = None) -> list[CommitRecord]:
        """遍历仓库历史并返回全部（或 ``since`` 之后）的文件级改动记录。"""
        try:
            repo = _git.Repo(str(repo_path))
        except Exception as exc:
            raise GitError(f"无法打开仓库 {repo_path}: {exc}") from exc

        kwargs: dict = {}
        if since:
            kwargs["since"] = since

        records: list[CommitRecord] = []
        for commit in repo.iter_commits(**kwargs):
            author = commit.author.name
            timestamp = int(commit.committed_datetime.timestamp())

            for path, stats in commit.stats.files.items():
                records.append(
                    CommitRecord(
                        author=author or "",
                        timestamp=timestamp,
                        file_path=str(path),
                        added=stats.get("insertions", 0),
                        deleted=stats.get("deletions", 0),
                    )
                )

        return records
