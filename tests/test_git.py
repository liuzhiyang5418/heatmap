"""Git 采集层的单元测试。"""

from __future__ import annotations

from pathlib import Path

import git as _git

from githotmap.core.git import CommitRecord, GitHistory, _normalize_since

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_commit_record_churn() -> None:
    r = CommitRecord(commit_hash="abc123", author="Alice", timestamp=1700000000, file_path="a.py", added=10, deleted=2)
    assert r.churn == 12


def test_commit_record_zero_churn() -> None:
    r = CommitRecord(commit_hash="abc123", author="Bob", timestamp=1700000000, file_path="b.bin", added=0, deleted=0)
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
        key = (r.commit_hash, r.author, r.timestamp, r.file_path)
        assert key not in seen, f"duplicate: {key}"
        seen.add(key)


def test_git_history_preserves_non_ascii_paths(tmp_path: Path) -> None:
    """M4-2 回归：非 ASCII 路径不应被 core.quotepath 转义成八进制。

    git 默认 ``core.quotepath=true`` 会把中文文件名输出成 C 风格八进制转义，
    与扫描器读到的真实 UTF-8 路径键失配、历史指标静默归零。采集层必须关闭
    quotepath，让文件路径原样返回。
    """
    repo = _git.Repo.init(tmp_path / "repo")
    workdir = repo.working_tree_dir
    assert workdir is not None
    (Path(workdir) / "中文模块.py").write_text("print(1)\n", encoding="utf-8")
    repo.index.add(["中文模块.py"])
    actor = _git.Actor("alice", "alice@example.com")
    repo.index.commit("init 中文", author=actor, committer=actor)

    records = GitHistory().collect(workdir)
    paths = [r.file_path for r in records]

    assert "中文模块.py" in paths
    # 不应出现 quotepath 的八进制转义形态（以引号 + 反斜杠开头）
    assert not any(p.startswith('"\\') for p in paths)
    repo.close()


def test_git_history_survives_shallow_clone(tmp_path: Path) -> None:
    """M4-6 回归：浅克隆边界提交缺少父对象，采集应降级而非整次崩溃。

    浅克隆（``--depth 1``）里的 HEAD 提交其父对象从未 fetch，``commit.stats``
    会抛 ``GitCommandError``。采集层应在该提交上降级为空改动，而不是让分析
    失败。
    """
    src = _git.Repo.init(tmp_path / "src")
    workdir = src.working_tree_dir
    assert workdir is not None
    f = Path(workdir) / "a.py"
    f.write_text("l1\n", encoding="utf-8")
    src.index.add(["a.py"])
    actor = _git.Actor("alice", "alice@example.com")
    src.index.commit("c1", author=actor, committer=actor)
    f.write_text("l1\nl2\n", encoding="utf-8")
    src.index.add(["a.py"])
    src.index.commit("c2", author=actor, committer=actor)

    dst = str(tmp_path / "shallow")
    _git.Repo.clone_from(workdir, dst, depth=1)

    records = GitHistory().collect(dst)
    # 关键断言：不抛异常；浅克隆边界提交的改动被降级，返回合法列表。
    assert isinstance(records, list)
    src.close()


def test_normalize_since_bare_date() -> None:
    """M4-1 回归：裸日期应补成显式 UTC 零点，而不是交给 git 补当天当前时刻。"""
    assert _normalize_since("2026-09-17") == "2026-09-17 00:00:00 +0000"


def test_normalize_since_full_timestamp_unchanged() -> None:
    """完整时间戳（ISO/Z 后缀）不应被改写。"""
    assert _normalize_since("2026-09-20T00:00:00Z") == "2026-09-20T00:00:00Z"


def test_normalize_since_none_returns_none() -> None:
    assert _normalize_since(None) is None


def test_git_history_skips_merge_commits(tmp_path: Path) -> None:
    """M4-5 回归：merge 提交不应把带入分支的改动计给 merge 者。

    构造 master 与 feature 分叉后 merge，产生的 merge commit 应被采集层跳过，
    其 churn 不会进入任何记录。
    """
    repo = _git.Repo.init(tmp_path / "repo")
    workdir = repo.working_tree_dir
    assert workdir is not None

    def commit_file(name: str, content: str, message: str) -> None:
        (Path(workdir) / name).write_text(content, encoding="utf-8")
        repo.index.add([name])
        actor = _git.Actor("alice", "alice@example.com")
        repo.index.commit(message, author=actor, committer=actor)

    commit_file("a.py", "l1\n", "c1 on master")
    repo.git.checkout("-b", "feature")
    commit_file("b.py", "l1\n", "c2 on feature")
    repo.git.checkout("master")
    commit_file("c.py", "l1\n", "c3 on master")

    # feature 与 master 已分叉，merge 会生成一个双父 merge commit。
    # `git merge` 不接受 author/committer 参数，只能查仓库配置，
    # 因此在临时仓库内写局部身份，避免测试依赖运行机器的全局 git 配置。
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "alice")
        cw.set_value("user", "email", "alice@example.com")
    repo.git.merge("feature")
    merge_commit = repo.head.commit
    assert len(merge_commit.parents) == 2

    records = GitHistory().collect(workdir)
    hashes = {r.commit_hash for r in records}
    assert merge_commit.hexsha not in hashes
    assert hashes, "非 merge 提交仍应被采集"
    repo.close()
