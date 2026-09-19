"""历史数据分析层：在基础采集之上做贡献者、分支、知识孤岛等深度分析。

本模块是 Member 4（Git History Analyzer）的第二部分交付物——采集由
:class:`~githotmap.core.git.GitPythonHistory` 负责，这里专注于**分析**：

- :func:`top_contributors` —— 贡献者排名（按提交数 / 改动量）；
- :func:`branch_activity` —— 分支活跃度（最近提交、提交数）；
- :func:`knowledge_islands` —— 知识孤岛检测（只有 1 位贡献者的文件）；
- :func:`file_ownership` —— 文件所有权（每个文件的主要贡献者及占比）；
- :func:`commit_frequency` —— 提交频率趋势（按天 / 小时分组）。

全部函数接收 ``git.Repo`` 对象（调用方已打开的仓库），返回纯数据结构，
不直接依赖 :class:`~githotmap.core.git.CommitRecord`，因为它们需要 commit hash、
message、tree 等 ``CommitRecord`` 不携带的字段。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import git as _git


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ContributorStats:
    """单个贡献者的聚合统计。"""

    name: str
    email: str
    commits: int
    total_added: int
    total_deleted: int

    @property
    def churn(self) -> int:
        return self.total_added + self.total_deleted


@dataclass(slots=True)
class BranchActivity:
    """单个分支的活跃度快照。"""

    name: str
    commit_count: int
    last_commit_datetime: datetime
    last_author: str
    last_message: str


@dataclass(slots=True)
class FileOwnership:
    """单个文件的所有权分布。"""

    file_path: str
    contributors: dict[str, int]  # author -> churn
    dominant_author: str
    dominant_ratio: float  # 主要贡献者的改动量占比 [0, 1]


@dataclass(slots=True)
class CommitFrequency:
    """时间维度的提交计数。"""

    # key 是 date(YYYY-MM-DD) 或 hour(0-23)，value 是提交次数
    counts: dict[str, int]
    total_commits: int


# ---------------------------------------------------------------------------
# 1. 贡献者排名
# ---------------------------------------------------------------------------


def top_contributors(
    repo_path: str | Path,
    top_n: int = 20,
    since: str | None = None,
) -> list[ContributorStats]:
    """按总改动量（churn = added + deleted）降序返回贡献者排名。"""
    repo = _git.Repo(str(repo_path))

    # 贡献者 -> {commits, added, deleted}
    agg: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"commits": 0, "added": 0, "deleted": 0}
    )

    kwargs: dict = {}
    if since:
        kwargs["since"] = since

    for commit in repo.iter_commits(**kwargs):
        key = (commit.author.name, commit.author.email)
        agg[key]["commits"] += 1
        for stats in commit.stats.files.values():
            agg[key]["added"] += stats.get("insertions", 0)
            agg[key]["deleted"] += stats.get("deletions", 0)

    # 排序：先按 churn 降序，再按 commits 降序
    ranked = sorted(
        agg.items(),
        key=lambda kv: (kv[1]["added"] + kv[1]["deleted"], kv[1]["commits"]),
        reverse=True,
    )

    result = [
        ContributorStats(
            name=name,
            email=email,
            commits=data["commits"],
            total_added=data["added"],
            total_deleted=data["deleted"],
        )
        for (name, email), data in ranked[:top_n]
    ]
    return result


# ---------------------------------------------------------------------------
# 2. 分支活跃度
# ---------------------------------------------------------------------------


def branch_activity(repo_path: str | Path) -> list[BranchActivity]:
    """遍历所有本地分支，返回各自的活跃度快照。"""
    repo = _git.Repo(str(repo_path))
    results: list[BranchActivity] = []

    for branch in repo.branches:
        # iter_commits 的 revision 参数可以是 branch 对象
        commits = list(repo.iter_commits(rev=branch, max_count=1))
        if not commits:
            continue
        last = commits[0]

        # 粗略估算：直接遍历全部可能比较慢，这里用 branch.commit_count() 不可靠，
        # 实际项目建议限制在 master/main 等关键分支上。
        # 为避免性能问题，这里用 rev-list --count 拿 commit_count。
        try:
            count_text = repo.git.rev_list("--count", branch.name).strip()
            commit_count = int(count_text)
        except Exception:
            commit_count = 0

        results.append(
            BranchActivity(
                name=branch.name,
                commit_count=commit_count,
                last_commit_datetime=last.committed_datetime,
                last_author=last.author.name,
                last_message=last.message.strip().split("\n")[0][:80],
            )
        )

    # 按最近提交时间降序
    results.sort(key=lambda b: b.last_commit_datetime, reverse=True)
    return results


# ---------------------------------------------------------------------------
# 3. 知识孤岛
# ---------------------------------------------------------------------------


def knowledge_islands(
    repo_path: str | Path,
    min_churn: int = 0,
    exclude_paths: Sequence[str] = (),
) -> list[FileOwnership]:
    """返回所有"知识孤岛"文件——只有 1 位贡献者改动过的文件。

    ``min_churn`` 过滤掉总改动量过低的文件（例如 README 的拼写修正）。
    ``exclude_paths`` 支持 fnmatch 风格的路径匹配排除。
    """
    import fnmatch

    repo = _git.Repo(str(repo_path))

    # file_path -> {author: churn}
    ownership: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for commit in repo.iter_commits():
        author = commit.author.name
        for path, stats in commit.stats.files.items():
            churn = stats.get("insertions", 0) + stats.get("deletions", 0)
            ownership[path][author] += churn

    islands: list[FileOwnership] = []
    for path, contrib in ownership.items():
        # 路径排除
        if any(fnmatch.fnmatch(path, pat) or pat in path for pat in exclude_paths):
            continue

        if len(contrib) != 1:
            continue
        author, churn = next(iter(contrib.items()))
        if churn < min_churn:
            continue

        islands.append(
            FileOwnership(
                file_path=path,
                contributors={author: churn},
                dominant_author=author,
                dominant_ratio=1.0,
            )
        )

    # 按孤岛的绝对改动量降序
    islands.sort(key=lambda o: next(iter(o.contributors.values())), reverse=True)
    return islands


# ---------------------------------------------------------------------------
# 4. 文件所有权
# ---------------------------------------------------------------------------


def file_ownership(repo_path: str | Path, top_n: int = 100) -> list[FileOwnership]:
    """返回每个文件的所有权分布，按主要贡献者的占比降序。"""
    repo = _git.Repo(str(repo_path))

    ownership: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for commit in repo.iter_commits():
        author = commit.author.name
        for path, stats in commit.stats.files.items():
            churn = stats.get("insertions", 0) + stats.get("deletions", 0)
            ownership[path][author] += churn

    results: list[FileOwnership] = []
    for path, contrib in ownership.items():
        total = sum(contrib.values())
        if total == 0:
            continue
        dominant = max(contrib, key=contrib.get)
        results.append(
            FileOwnership(
                file_path=path,
                contributors=dict(contrib),
                dominant_author=dominant,
                dominant_ratio=contrib[dominant] / total,
            )
        )

    # 按 dominant_ratio 降序，高占比 → 知识孤岛风险高
    results.sort(key=lambda r: r.dominant_ratio, reverse=True)
    return results[:top_n]


# ---------------------------------------------------------------------------
# 5. 提交频率
# ---------------------------------------------------------------------------


def commit_frequency(
    repo_path: str | Path,
    group_by: str = "day",
    since: str | None = None,
) -> CommitFrequency:
    """按时间维度统计提交频率。

    ``group_by`` 支持 ``"day"``（YYYY-MM-DD）和 ``"hour"``（0-23）两种分组。
    """
    repo = _git.Repo(str(repo_path))

    kwargs: dict = {}
    if since:
        kwargs["since"] = since

    counter: Counter[str] = Counter()
    for commit in repo.iter_commits(**kwargs):
        dt = commit.committed_datetime
        if group_by == "day":
            key = dt.strftime("%Y-%m-%d")
        elif group_by == "hour":
            key = str(dt.hour)
        else:
            raise ValueError(f"未知 group_by: {group_by!r}，可选 'day' / 'hour'")
        counter[key] += 1

    return CommitFrequency(
        counts=dict(counter),
        total_commits=sum(counter.values()),
    )
