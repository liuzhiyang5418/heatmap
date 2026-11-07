"""Git 数据采集层：用 GitPython 遍历提交历史并提取文件级改动。

只做一次 ``iter_commits`` 遍历，同时拿到作者、时间与 per-file 的
added/deleted/churn，产出 :class:`CommitRecord` 列表供 ``metrics`` 层聚合。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import git as _git

# ---------------------------------------------------------------------------
# 异常与数据类
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    """Git 命令执行失败时抛出，携带 stderr 以便诊断。"""


@dataclass(slots=True)
class CommitRecord:
    """单个提交对单个文件的一次改动记录。"""

    commit_hash: str
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


@contextmanager
def _open_repo(repo_path: str | Path) -> Iterator[_git.Repo]:
    """以统一口径打开仓库，结束后释放句柄。

    两件必须做对的事：

    - **关闭 ``core.quotepath``**：git 默认把非 ASCII 路径输出成 C 八进制转义，
      与扫描器读到的真实 UTF-8 路径键失配（历史指标静默归零），见
      ``docs/scanner-interface.md`` §4.1；
    - **用后 ``close()``**：GitPython 的 ``Repo`` 会常驻 ``git cat-file --batch``
      子进程，不关闭会逐次泄漏进程与 ``.git`` 句柄。
    """
    repo = _git.Repo(str(repo_path))
    try:
        repo.git.set_persistent_git_options(c="core.quotepath=false")
        yield repo
    finally:
        repo.close()


def _iter_file_changes(commit: _git.Commit) -> Iterator[tuple[str, dict[str, int]]]:
    """遍历单个提交的 per-file 改动；浅克隆边界缺失父对象时降级为空。

    浅克隆里边界提交的第一父从未被 fetch，``commit.stats`` 会抛
    ``GitCommandError``——这里降级跳过该提交，而不是让整次分析崩溃。

    键统一转为 ``str``（GitPython 的 ``Stats.files`` 键形如 ``PathLike``），
    值只保留 ``insertions`` / ``deletions`` 两个调用方实际用到的整数。
    """
    try:
        files = commit.stats.files
    except _git.GitCommandError:
        return
    for path, stats in files.items():
        yield str(path), {
            "insertions": stats.get("insertions", 0),
            "deletions": stats.get("deletions", 0),
        }


_BARE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_since(since: str | None) -> str | None:
    """把裸日期 ``YYYY-MM-DD`` 规范化为显式 UTC 时间。

    git 对 ``--since`` 的裸日期会补成「当天当前时刻」而非 00:00，用户会拿到
    随一天中时刻与机器时区而变的意外边界。这里统一补成 UTC 零点，与
    ``.timestamp()`` 的 UTC epoch 口径一致（缺陷总结 M4-1）。
    完整时间戳（含 ``T``/``Z`` 等后缀）原样返回。
    """
    if since is None:
        return None
    if _BARE_DATE_RE.fullmatch(since):
        return f"{since} 00:00:00 +0000"
    return since


def resolve_urn(repo_path: str | Path) -> str:
    """解析仓库的可移植身份标识（URN）。

    优先使用远端 origin URL（规范化为 ``git:host/owner/repo`` 形态），否则回退到
    本地绝对路径 ``local:<abs_path>``，保证跨机器缓存键稳定。
    """
    try:
        with _open_repo(repo_path) as repo:
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
        """遍历仓库历史并返回全部（或 ``since`` 之后）的文件级改动记录。

        仅遍历当前 ``HEAD`` 可达的历史；未合并的分支不纳入主指标（该口径与
        ``branch_activity`` 的全分支遍历不同，属有意设计，见缺陷总结 M4-7②）。
        """
        kwargs: dict = {}
        if since:
            kwargs["since"] = _normalize_since(since)

        records: list[CommitRecord] = []
        try:
            with _open_repo(repo_path) as repo:
                for commit in repo.iter_commits(**kwargs):
                    # 跳过 merge 提交：其 stats 对第一父 diff，会把带入的
                    # 分支改动全计给 merge 者（重复计数 + 错误归属，M4-5）。
                    if len(commit.parents) > 1:
                        continue
                    author = commit.author.name
                    timestamp = int(commit.committed_datetime.timestamp())

                    for path, stats in _iter_file_changes(commit):
                        records.append(
                            CommitRecord(
                                commit_hash=commit.hexsha,
                                author=author or "",
                                timestamp=timestamp,
                                file_path=str(path),
                                added=stats.get("insertions", 0),
                                deleted=stats.get("deletions", 0),
                            )
                        )
        except Exception as exc:
            raise GitError(f"无法打开仓库 {repo_path}: {exc}") from exc

        return records
