"""Git History Analyzer 深度分析模块的单元测试。

- 形状类测试用当前项目自身的仓库做冒烟验证（返回类型、字段非空、排序正确）；
- 行为类测试（since 过滤、分支统计）用 ``tmp_path`` 下现场构造的一次性仓库，
  作者、提交时间、分支指向完全可控，测试结果不受真实仓库历史增长影响。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import git as _git
import pytest

from githotmap.core.analysis import (
    BranchActivity,
    CommitFrequency,
    ContributorStats,
    FileOwnership,
    branch_activity,
    commit_frequency,
    file_ownership,
    knowledge_islands,
    top_contributors,
)

# 指向本项目根目录（git 仓库所在）
_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 临时仓库 fixture：提交历史完全可控，测完随 tmp_path 自动清理
# ---------------------------------------------------------------------------


def _utc(day: int, hour: int = 10) -> datetime:
    return datetime(2026, 9, day, hour, 0, tzinfo=timezone.utc)


def _commit_file(
    repo: _git.Repo,
    author: str,
    filename: str,
    content: str,
    when: datetime,
    message: str,
) -> _git.Commit:
    """在临时仓库中以指定作者和提交时间写入一次文件改动。"""
    workdir = repo.working_tree_dir
    assert workdir is not None  # init 出来的是非裸仓库
    path = Path(workdir) / filename
    path.write_text(content, encoding="utf-8")
    repo.index.add([filename])
    actor = _git.Actor(author, f"{author}@example.com")
    return repo.index.commit(
        message,
        author=actor,
        committer=actor,
        author_date=when,
        commit_date=when,
    )


@pytest.fixture()
def sample_repo(tmp_path: Path) -> Iterator[Path]:
    """构造提交历史完全确定的一次性仓库。

    时间线（均为 UTC）::

        alice  2026-09-01  新建 a.py（3 行）   ┐
        bob    2026-09-10  新建 b.py（2 行）   ├─ 默认分支
        alice  2026-09-20  a.py 追加 2 行      ┘

    另有 ``stable`` 分支指向 09-01 的第一条提交（仅 1 个提交）。

    ``tmp_path`` 是函数级 fixture：每个用例都拿到全新仓库、测完即删，
    用例之间不可能互相污染历史。
    """
    repo = _git.Repo.init(tmp_path / "sample")
    first = _commit_file(repo, "alice", "a.py", "l1\nl2\nl3\n", _utc(1), "init a")
    _commit_file(repo, "bob", "b.py", "x\ny\n", _utc(10), "add b")
    _commit_file(repo, "alice", "a.py", "l1\nl2\nl3\nl4\nl5\n", _utc(20), "update a")
    repo.create_head("stable", first)
    workdir = repo.working_tree_dir
    assert workdir is not None  # init 出来的是非裸仓库
    yield Path(workdir)
    # 显式释放 GitPython 持有的句柄，否则 Windows 下临时目录可能删不掉
    repo.close()


def test_top_contributors_returns_sorted_list() -> None:
    result = top_contributors(_REPO_ROOT, top_n=5)
    assert isinstance(result, list)
    assert len(result) >= 1  # 至少有组长 1 个贡献者
    assert isinstance(result[0], ContributorStats)

    # churn 应该降序
    for i in range(len(result) - 1):
        assert result[i].churn >= result[i + 1].churn

    # 字段完整性
    assert result[0].commits >= 1
    assert result[0].churn >= 0


def test_top_contributors_since_filter(sample_repo: Path) -> None:
    # since 之前的提交（alice 09-01、bob 09-10）都应被过滤，
    # 只保留 alice 09-20 对 a.py 的 2 行追加。
    result = top_contributors(sample_repo, since="2026-09-15")
    assert len(result) == 1
    stats = result[0]
    assert stats.name == "alice"
    assert stats.commits == 1
    assert stats.total_added == 2
    assert stats.total_deleted == 0

    # 不带 since 时三个提交、两位贡献者都应出现（证明过滤确实来自 since）
    full = top_contributors(sample_repo)
    assert {c.name for c in full} == {"alice", "bob"}
    alice = next(c for c in full if c.name == "alice")
    assert alice.commits == 2


def test_top_contributors_since_boundary_day_is_inclusive(sample_repo: Path) -> None:
    # git 的 --since 对裸日期按本地时区的当天 00:00 解释，语义含当天：
    # alice 09-20 10:00(UTC) 的提交应当被包含。
    result = top_contributors(sample_repo, since="2026-09-20")
    assert len(result) == 1
    assert result[0].name == "alice"
    assert result[0].commits == 1
    assert result[0].total_added == 2


def test_top_contributors_since_all_filtered_returns_empty(sample_repo: Path) -> None:
    # since 晚于全部提交时必须返回真空列表，而不是零值聚合对象。
    result = top_contributors(sample_repo, since="2026-10-01")
    assert result == []


def test_branch_activity_returns_branches(sample_repo: Path) -> None:
    result = branch_activity(sample_repo)
    assert isinstance(result, list)
    assert len(result) == 2  # 默认分支 + stable
    assert isinstance(result[0], BranchActivity)

    by_name = {b.name: b for b in result}
    assert "stable" in by_name
    assert by_name["stable"].commit_count == 1  # stable 只指向 09-01 的提交

    # 默认分支包含全部 3 个提交，且最新（09-20）应排第一
    default_name = next(name for name in by_name if name != "stable")
    assert by_name[default_name].commit_count == 3
    assert result[0].name == default_name

    # 最近提交时间降序
    for i in range(len(result) - 1):
        assert result[i].last_commit_datetime >= result[i + 1].last_commit_datetime


def test_knowledge_islands_detects_single_contributor_files() -> None:
    result = knowledge_islands(_REPO_ROOT, min_churn=0)
    assert isinstance(result, list)
    for o in result:
        assert isinstance(o, FileOwnership)
        assert len(o.contributors) == 1
        assert o.dominant_ratio == 1.0
        assert o.file_path  # 非空路径


def test_file_ownership_fields() -> None:
    result = file_ownership(_REPO_ROOT, top_n=50)
    assert isinstance(result, list)
    for o in result:
        assert isinstance(o, FileOwnership)
        assert 0.0 <= o.dominant_ratio <= 1.0
        assert sum(o.contributors.values()) > 0
        assert o.dominant_author in o.contributors


def test_file_ownership_dominant_ratio_sum_to_one() -> None:
    """dominant_ratio 应该等于该作者 churn 占总 churn 的比例。"""
    result = file_ownership(_REPO_ROOT, top_n=50)
    for o in result:
        total = sum(o.contributors.values())
        if total == 0:
            continue
        expected = o.contributors[o.dominant_author] / total
        assert abs(o.dominant_ratio - expected) < 0.001


def test_commit_frequency_day() -> None:
    result = commit_frequency(_REPO_ROOT, group_by="day")
    assert isinstance(result, CommitFrequency)
    assert result.total_commits >= 2  # 至少组长 initial commit + 我的修复
    assert result.total_commits == sum(result.counts.values())
    for key in result.counts:
        assert len(key) == 10  # YYYY-MM-DD 长度


def test_commit_frequency_hour() -> None:
    result = commit_frequency(_REPO_ROOT, group_by="hour")
    assert isinstance(result, CommitFrequency)
    for key in result.counts:
        h = int(key)
        assert 0 <= h <= 23


def test_commit_frequency_invalid_group() -> None:
    try:
        commit_frequency(_REPO_ROOT, group_by="month")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid group_by")
