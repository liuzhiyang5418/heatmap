"""Git 采集层的单元测试。"""

from __future__ import annotations

from pathlib import Path

from githotmap.core.git import CommitRecord, GitHistory

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_commit_record_churn() -> None:
    r = CommitRecord(author="Alice", timestamp=1700000000, file_path="a.py", added=10, deleted=2)
    assert r.churn == 12


def test_commit_record_zero_churn() -> None:
    r = CommitRecord(author="Bob", timestamp=1700000000, file_path="b.bin", added=0, deleted=0)
    assert r.churn == 0


def test_git_history_collects_records() -> None:
    """用当前项目自身的仓库验证 GitHistory 能正常采集。"""
    history = GitHistory()
    records = history.collect(_REPO_ROOT)
    assert len(records) >= 2  # 至少 initial commit + 我的改动

    # 每条记录字段完整性
    for r in records:
        assert r.author
        assert r.timestamp > 0
        assert r.file_path
        assert r.added >= 0
        assert r.deleted >= 0
        assert r.churn >= 0


def test_git_history_collect_with_since() -> None:
    """since 过滤应该只返回指定时间之后的记录。"""
    history = GitHistory()
    records = history.collect(_REPO_ROOT, since="2026-09-17")
    for r in records:
        assert r.timestamp > 0
        # 2026-09-17 00:00:00 UTC ≈ 1789603200
        assert r.timestamp >= 1789603200


def test_git_history_returns_deduplicated_files_per_commit() -> None:
    """同一个文件在同一次提交里不应该出现两次。"""
    history = GitHistory()
    records = history.collect(_REPO_ROOT)
    seen = set()
    for r in records:
        key = (r.author, r.timestamp, r.file_path)
        assert key not in seen, f"duplicate: {key}"
        seen.add(key)
