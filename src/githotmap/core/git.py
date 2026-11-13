"""Git 数据采集层：用 GitPython 遍历提交历史并提取文件级改动。

只做一次 ``iter_commits`` 遍历，同时拿到作者、时间与 per-file 的
added/deleted/churn，产出 :class:`CommitRecord` 列表供 ``metrics`` 层聚合。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        """转成只含 JSON 原生类型的字典，供 M6 ``json.dumps``。"""
        return {
            "commit_hash": self.commit_hash,
            "author": self.author,
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "added": self.added,
            "deleted": self.deleted,
        }


#: 浅克隆边界提交缺失父对象、per-file diff 不可得（NFR-2 原因码）。
CODE_SHALLOW_CLONE = "shallow-clone"
CODE_EMPTY_REPO = "empty-repo"

#: git 采集阶段的降级原因码（NFR-2）。
#:
#: 这是「git 采集阶段」降级原因码的单一来源，取值只能追加、不得修改或删除，
#: 与 scanner 的 ``Limitation``（严格限定在扫描阶段）互相独立；流水线接入
#: 约定见 ``docs/git-interface.md``，公共诊断模型应对齐这些字符串取值。
GIT_DEGRADATION_CODES: tuple[str, ...] = (CODE_SHALLOW_CLONE, CODE_EMPTY_REPO)


@dataclass(slots=True)
class GitDegradation:
    """单条降级记录（NFR-2：不静默降级，每次跳过都带可机器读取的原因码）。

    字段形状与 NFR 计划 WP-0 的 ``core.diagnostics.Degradation`` 对齐，
    便于 M5 的流水线落地后以一次映射接入：

    - ``stage``  ：固定 ``"git"``，标明降级发生在 git 采集阶段；
    - ``code``   ：原因码，取值限定为 :data:`GIT_DEGRADATION_CODES`；
    - ``path``   ：浅克隆场景为边界提交的完整 SHA，空仓库为 ``None``；
    - ``summary``：一行人类可读说明；**只含固定文本与异常类名**（不含异常
      消息），保证跨平台、跨运行的可复现性（NFR-3）。
    """

    code: str
    path: str | None
    summary: str
    stage: str = "git"

    def to_dict(self) -> dict[str, Any]:
        """转成只含 JSON 原生类型的字典，供 M6 ``json.dumps``。"""
        return {
            "stage": self.stage,
            "code": self.code,
            "path": self.path,
            "summary": self.summary,
        }


@dataclass(slots=True)
class GitCollectResult:
    """``collect_with_degradations`` 的完整产出：改动记录 + 降级记录。"""

    records: list[CommitRecord] = field(default_factory=list)
    degradations: list[GitDegradation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "degradations": [d.to_dict() for d in self.degradations],
        }


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


def _commit_files(commit: _git.Commit) -> dict[str, dict[str, int]] | None:
    """返回单个提交的 per-file 改动映射；diff 不可得（浅克隆边界）时返回 ``None``。

    浅克隆里边界提交的第一父从未被 fetch，``commit.stats`` 会抛
    ``GitCommandError``。仅确认是边界且第一父缺失时收敛为 ``None``，其他
    Git 错误继续抛出。由调用方决定是降级留痕
    （:meth:`GitHistory.collect_with_degradations`）还是静默跳过
    （:func:`_iter_file_changes`，供历史分析层沿用）。

    键统一转为 ``str``（GitPython 的 ``Stats.files`` 键形如 ``PathLike``），
    值只保留 ``insertions`` / ``deletions`` 两个调用方实际用到的整数。
    """
    try:
        files = commit.stats.files
    except _git.GitCommandError:
        shallow_file = Path(commit.repo.common_dir) / "shallow"
        if shallow_file.is_file():
            boundaries = shallow_file.read_text(encoding="ascii").splitlines()
            if (
                commit.hexsha in boundaries
                and commit.parents
                and not commit.repo.odb.has_object(commit.parents[0].binsha)
            ):
                return None
        raise
    result: dict[str, dict[str, int]] = {}
    for path, stats in files.items():
        result[str(path)] = {
            "insertions": int(stats.get("insertions", 0)),
            "deletions": int(stats.get("deletions", 0)),
        }
    return result


def _iter_file_changes(commit: _git.Commit) -> Iterator[tuple[str, dict[str, int]]]:
    """遍历单个提交的 per-file 改动；diff 不可得时降级为空（不产出）。

    浅克隆边界提交缺失父对象、diff 不可得时静默跳过——该静默口径供历史分析层
    （``analysis``）沿用；采集门面的可审计口径见
    :meth:`GitHistory.collect_with_degradations`。
    """
    files = _commit_files(commit)
    if files is None:
        return
    yield from files.items()


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
            origin = next((remote for remote in repo.remotes if remote.name == "origin"), None)
            url = origin.url if origin is not None else ""
    except (_git.GitError, OSError, ValueError):
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
        """遍历仓库历史并返回文件级改动记录（仅记录，不含降级信息）。

        如需降级留痕，改用 :meth:`collect_with_degradations`。
        """
        return self.collect_with_degradations(repo_path, since=since).records

    def collect_with_degradations(
        self, repo_path: str | Path, since: str | None = None
    ) -> GitCollectResult:
        """遍历仓库历史并返回改动记录与降级记录（NFR-2 可审计口径）。

        仅遍历当前 ``HEAD`` 可达的历史；未合并的分支不纳入主指标（该口径与
        ``branch_activity`` 的全分支遍历不同，属有意设计，见缺陷总结 M4-7②）。
        浅克隆边界提交的 per-file diff 不可得时降级留痕（``shallow-clone``），
        而非静默丢失。
        """
        kwargs: dict[str, Any] = {}
        if since:
            normalized = _normalize_since(since)
            if normalized is not None:
                kwargs["since"] = normalized

        records: list[CommitRecord] = []
        degradations: list[GitDegradation] = []
        try:
            with _open_repo(repo_path) as repo:
                if not repo.head.is_valid():
                    return GitCollectResult(
                        degradations=[
                            GitDegradation(
                                code=CODE_EMPTY_REPO,
                                path=None,
                                summary="repository has no commits",
                            )
                        ]
                    )
                for commit in repo.iter_commits(**kwargs):
                    # 跳过 merge 提交：其 stats 对第一父 diff，会把带入的
                    # 分支改动全计给 merge 者（重复计数 + 错误归属，M4-5）。
                    if len(commit.parents) > 1:
                        continue
                    author = commit.author.name
                    timestamp = int(commit.committed_datetime.timestamp())

                    files = _commit_files(commit)
                    if files is None:
                        # 浅克隆边界：diff 不可得，降级留痕而非静默（NFR-2）。
                        degradations.append(
                            GitDegradation(
                                code=CODE_SHALLOW_CLONE,
                                path=commit.hexsha,
                                summary=f"diff unavailable: {_git.GitCommandError.__name__}",
                            )
                        )
                        continue
                    for path, stats in files.items():
                        records.append(
                            CommitRecord(
                                commit_hash=commit.hexsha,
                                author=author or "",
                                timestamp=timestamp,
                                file_path=path,
                                added=stats.get("insertions", 0),
                                deleted=stats.get("deletions", 0),
                            )
                        )
        except Exception as exc:
            raise GitError(f"无法采集仓库 {repo_path}: {exc}") from exc

        degradations.sort(key=lambda d: (d.path or "", d.code))
        return GitCollectResult(records=records, degradations=degradations)
