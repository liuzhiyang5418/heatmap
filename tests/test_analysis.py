"""Git History Analyzer 深度分析模块的单元测试。

用当前项目自身的仓库作为 fixture，确保每个分析函数至少有
基本的形状正确性（返回类型、字段非空、排序符合预期）。
"""

from __future__ import annotations

from pathlib import Path

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


def test_top_contributors_since_filter() -> None:
    # since 设为未来日期时，过滤结果应为空（不依赖具体提交历史）。
    # 注意：git approxidate 对 2999+ 的年份解析失败会退化为不过滤，故用 2099。
    result = top_contributors(_REPO_ROOT, since="2099-01-01")
    assert result == []
    # since 设为远古日期时，结果应与不带 since 的全量统计一致。
    all_contributors = top_contributors(_REPO_ROOT)
    since_epoch = top_contributors(_REPO_ROOT, since="1970-01-01")
    assert len(since_epoch) >= len(all_contributors)


def test_branch_activity_returns_branches() -> None:
    result = branch_activity(_REPO_ROOT)
    assert isinstance(result, list)
    assert len(result) >= 1  # 至少包含 main（克隆环境下远端分支不可见）
    assert isinstance(result[0], BranchActivity)

    # 最新分支应该排最前
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
