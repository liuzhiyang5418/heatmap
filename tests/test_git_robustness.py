"""Git 采集层 NFR-2/NFR-3 故障注入测试套件（WP-3）。

验证 Git 采集接口：可恢复边界返回原因码，硬失败保留异常链。
每个降级场景断言三件事：

1. 不抛未捕获异常（NFR-2.1 崩溃率 0）；
2. 降级必带非空原因码且与预期一致（NFR-2.2 覆盖率 100%）；
3. 检测结果正确。

外加一次双跑 ``to_dict()`` 逐字节相等的确定性用例（NFR-3）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import PropertyMock, patch

import git as _git
import pytest

from githotmap.core.git import (
    CODE_EMPTY_REPO,
    CODE_SHALLOW_CLONE,
    GIT_DEGRADATION_CODES,
    GitCollectResult,
    GitError,
    GitHistory,
    _open_repo,
)


def _make_repo(root: Path) -> tuple[_git.Repo, str]:
    """初始化仓库并返回 ``(Repo, 工作目录字符串)``。"""
    repo = _git.Repo.init(root)
    wd = repo.working_tree_dir
    assert wd is not None
    return repo, str(wd)


def _commit(repo: _git.Repo, wd: str, name: str, content: str, message: str) -> None:
    """写文件、加入索引并提交（用显式 Actor，不依赖机器全局 git 配置）。"""
    (Path(wd) / name).write_text(content, encoding="utf-8")
    repo.index.add([name])
    actor = _git.Actor("alice", "alice@example.com")
    repo.index.commit(message, author=actor, committer=actor)


def _make_shallow_clone(src_wd: str, dst: str) -> _git.Repo:
    """用 ``git clone --depth 1 <file://url>`` 构造真浅克隆。

    GitPython 的 ``Repo.clone_from(..., depth=1)`` 在本地路径上不会真正截断
    历史（本地克隆默认走 local 优化），必须显式用 ``file://`` URL 强制走
    fetch 协议，``--depth`` 才会生效、边界提交的父对象才不会被 fetch。
    """
    url = Path(src_wd).as_uri()
    subprocess.run(
        ["git", "clone", "--depth", "1", url, dst],
        check=True,
        capture_output=True,
    )
    return _git.Repo(dst)


def test_shallow_clone_records_degradation(tmp_path: Path) -> None:
    """浅克隆边界提交 diff 不可得 → 降级留痕 code=shallow-clone，而非崩溃。"""
    repo, wd = _make_repo(tmp_path / "src")
    _commit(repo, wd, "a.py", "l1\n", "c1")
    _commit(repo, wd, "a.py", "l1\nl2\n", "c2")

    dst = str(tmp_path / "shallow")
    shallow = _make_shallow_clone(wd, dst)

    result = GitHistory().collect_with_degradations(dst)

    assert isinstance(result, GitCollectResult)
    # 边界提交的 diff 不可得：不改动记录，只留一条降级（NFR-2 不静默）。
    assert result.records == []
    assert len(result.degradations) == 1
    d = result.degradations[0]
    assert d.code == CODE_SHALLOW_CLONE
    assert d.code in GIT_DEGRADATION_CODES
    assert d.summary == "diff unavailable: GitCommandError"
    assert d.stage == "git"
    assert d.path is not None and len(d.path) == 40

    repo.close()
    shallow.close()


def test_shallow_clone_legacy_collect_still_returns_list(tmp_path: Path) -> None:
    """旧接口 collect() 仍是薄封装：浅克隆上返回 list 而非崩溃（M4-6 回归）。"""
    repo, wd = _make_repo(tmp_path / "src")
    _commit(repo, wd, "a.py", "l1\n", "c1")
    _commit(repo, wd, "a.py", "l1\nl2\n", "c2")

    dst = str(tmp_path / "shallow")
    shallow = _make_shallow_clone(wd, dst)

    records = GitHistory().collect(dst)
    assert isinstance(records, list)

    repo.close()
    shallow.close()


def test_collect_non_repo_raises_giterror(tmp_path: Path) -> None:
    """非 git 目录是硬失败：抛明确的 GitError，而非未捕获异常。"""
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    (not_a_repo / "a.py").write_text("l1\n", encoding="utf-8")

    with pytest.raises(GitError):
        GitHistory().collect(not_a_repo)


def test_collect_empty_repo_returns_no_records(tmp_path: Path) -> None:
    """空仓库明确标记 empty-repo，旧接口仍兼容空列表。"""
    repo, wd = _make_repo(tmp_path / "empty")
    result = GitHistory().collect_with_degradations(wd)

    assert result.records == []
    assert len(result.degradations) == 1
    d = result.degradations[0]
    assert d.code == CODE_EMPTY_REPO
    assert d.code in GIT_DEGRADATION_CODES
    assert d.path is None
    assert d.stage == "git"
    assert GitHistory().collect(wd) == []
    assert json.loads(json.dumps(result.to_dict())) == result.to_dict()
    repo.close()


def test_normal_repo_produces_no_degradations(tmp_path: Path) -> None:
    """有完整父对象的正常仓库：diff 全部可得，无降级记录。"""
    repo, wd = _make_repo(tmp_path / "repo")
    _commit(repo, wd, "a.py", "l1\n", "c1")
    _commit(repo, wd, "a.py", "l1\nl2\n", "c2")

    result = GitHistory().collect_with_degradations(wd)

    assert result.degradations == []
    assert len(result.records) >= 2  # c1 改 a.py + c2 改 a.py
    repo.close()


def test_collect_is_deterministic(tmp_path: Path) -> None:
    """NFR-3：同一仓库双跑，to_dict() 逐字节相等。"""
    repo, wd = _make_repo(tmp_path / "repo")
    _commit(repo, wd, "a.py", "l1\n", "c1")
    _commit(repo, wd, "中文模块.py", "print(1)\n", "c2")

    first = GitHistory().collect_with_degradations(wd)
    second = GitHistory().collect_with_degradations(wd)

    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )
    repo.close()


def test_degradation_to_dict_is_json_native(tmp_path: Path) -> None:
    """降级记录的 to_dict() 只含 JSON 原生类型（供 M6 json.dumps）。"""
    repo, wd = _make_repo(tmp_path / "src")
    _commit(repo, wd, "a.py", "l1\n", "c1")
    _commit(repo, wd, "a.py", "l1\nl2\n", "c2")
    dst = str(tmp_path / "shallow")
    shallow = _make_shallow_clone(wd, dst)

    result = GitHistory().collect_with_degradations(dst)
    payload = result.to_dict()

    assert json.dumps(payload)
    assert list(payload.keys()) == ["records", "degradations"]
    d0 = payload["degradations"][0]
    assert list(d0.keys()) == ["stage", "code", "path", "summary"]

    repo.close()
    shallow.close()


@pytest.mark.parametrize("shallow", [False, True])
def test_diff_failure_is_not_misreported_as_shallow(tmp_path: Path, shallow: bool) -> None:
    """完整仓库和浅仓库的非边界提交出错时，都必须保留真实失败。"""
    with _git.Repo.init(tmp_path / "src") as repo:
        wd = repo.working_tree_dir
        assert wd is not None
        wd = str(wd)
        for i in range(3):
            _commit(repo, wd, "a.py", "line\n" * (i + 1), f"c{i}")
        target = wd
        if shallow:
            target = str(tmp_path / "shallow")
            subprocess.run(
                ["git", "clone", "--depth", "2", Path(wd).as_uri(), target],
                check=True,
                capture_output=True,
            )
        failure = _git.GitCommandError("git diff", 128, stderr="fatal: bad object")
        with (
            patch.object(_git.Commit, "stats", new_callable=PropertyMock, side_effect=failure),
            pytest.raises(GitError) as caught,
        ):
            GitHistory().collect_with_degradations(target)
        assert caught.value.__cause__ is failure
        assert "bad object" in str(caught.value)


@pytest.mark.parametrize("fail", [False, True])
def test_repo_is_closed_on_success_and_failure(tmp_path: Path, fail: bool) -> None:
    """正常完成和中途异常都释放 Repo 资源。"""
    repo = _git.Repo.init(tmp_path / "repo")
    with (
        patch("githotmap.core.git._git.Repo", return_value=repo),
        patch.object(repo, "close", wraps=repo.close) as close,
    ):
        if fail:
            with pytest.raises(RuntimeError, match="injected"), _open_repo(tmp_path / "repo"):
                raise RuntimeError("injected")
        else:
            with _open_repo(tmp_path / "repo"):
                pass
        close.assert_called_once()
