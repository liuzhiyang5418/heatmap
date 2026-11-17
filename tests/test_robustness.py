"""End-to-end fault and boundary scenarios for NFR-2."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import PropertyMock, patch

import git
import pytest

from githotmap.clock import FixedClock
from githotmap.core.pipeline import AnalysisPipeline


def _repo(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Fixture", "-c",
         "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
        check=True,
    )
    return root


def _result(repo: Path):
    return AnalysisPipeline(
        clock=FixedClock(datetime(2030, 1, 1, tzinfo=timezone.utc))
    ).run(repo)


def _assert_accounting(result) -> None:
    assert result.stats.files_matched >= result.stats.files_emitted
    assert result.stats.files_degraded == len(
        {d.path for d in result.stats.degradations if d.path}
        | {f.path for f in result.files if f.limitations}
    )
    assert all(d.code.value for d in result.stats.degradations)


def test_non_ascii_path_is_analyzed(tmp_path: Path) -> None:
    result = _result(_repo(tmp_path / "repo", {"中文模块.py": b"def run():\n    return 1\n"}))
    file = next(item for item in result.files if item.path == "中文模块.py")
    assert file.commits > 0 and file.mode_score > 0
    _assert_accounting(result)


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("binary.py", b"\x00\x01binary", "not-text"),
        ("large.py", b"x = 1\n" * 400_000, "too-large"),
        ("broken.py", b"def broken(:\n pass\n", "syntax-error"),
        ("gbk.py", "# coding: gbk\n名 = '值'\n".encode("gbk"), None),
    ],
    ids=["binary", "large", "syntax-error", "gbk-source"],
)
def test_file_content_boundaries_are_audited(
    tmp_path: Path, name: str, content: bytes, expected: str | None
) -> None:
    result = _result(_repo(tmp_path / "repo", {name: content}))
    codes = [item.code.value for item in result.stats.degradations]
    if expected is None:
        assert codes == []
    else:
        assert expected in codes
    _assert_accounting(result)


def test_symlink_is_skipped_with_reason(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo", {"base.py": b"print(1)\n"})
    link = repo / "linked.py"
    try:
        os.symlink(repo / "base.py", link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    result = _result(repo)
    assert any(d.code.value == "symlink" and d.path == "linked.py" for d in result.stats.degradations)
    _assert_accounting(result)


def test_empty_repository_has_reason_code(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    result = _result(repo)
    assert [d.code.value for d in result.stats.degradations] == ["empty-repo"]
    _assert_accounting(result)


def test_non_git_directory_degrades_without_crashing(tmp_path: Path) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "one.py").write_text("print(1)\n", encoding="utf-8")
    result = _result(repo)
    assert any(d.code.value == "stage-failed" for d in result.stats.degradations)


def test_stage_failure_detail_does_not_expose_machine_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path / "repo", {"a.py": b"print(1)\n"})
    from githotmap.core.git import GitHistory

    def fail_collect(*args, **kwargs):
        raise OSError(f"failed to read {tmp_path / 'private-host-path'}")

    monkeypatch.setattr(GitHistory, "collect_with_degradations", fail_collect)
    result = _result(repo)
    failure = next(d for d in result.stats.degradations if d.code.value == "stage-failed")
    assert failure.detail == "OSError"
    assert str(tmp_path) not in failure.detail


def test_shallow_clone_degradation_reaches_analysis_result(tmp_path: Path) -> None:
    source = _repo(tmp_path / "source", {"a.py": b"x = 1\n"})
    with git.Repo(source) as repo:
        file = source / "a.py"
        file.write_text("x = 1\ny = 2\n", encoding="utf-8")
        repo.index.add(["a.py"])
        actor = git.Actor("Fixture", "fixture@example.invalid")
        repo.index.commit("second", author=actor, committer=actor)
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth", "1", source.as_uri(), str(shallow)],
        check=True,
        capture_output=True,
    )
    result = _result(shallow)
    assert any(d.code.value == "shallow-clone" for d in result.stats.degradations)
    _assert_accounting(result)


def test_unreadable_file_gets_reason_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path / "repo", {"blocked.py": b"print(1)\n"})
    target = (repo / "blocked.py").resolve()
    original = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path.resolve() == target:
            raise PermissionError("injected")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    result = _result(repo)
    assert any(d.code.value == "unreadable" and d.path == "blocked.py" for d in result.stats.degradations)
    _assert_accounting(result)


def test_deep_directory_does_not_crash(tmp_path: Path) -> None:
    nested = "/".join(f"d{i:02d}" for i in range(24)) + "/deep.py"
    result = _result(_repo(tmp_path / "repo", {nested: b"print(1)\n"}))
    assert result.files
    _assert_accounting(result)


def test_git_object_failure_becomes_stage_diagnostic(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo", {"a.py": b"print(1)\n"})
    failure = git.GitCommandError("git diff", 128, stderr="fatal: bad object")
    with patch.object(git.Commit, "stats", new_callable=PropertyMock, side_effect=failure):
        result = _result(repo)
    assert any(d.stage == "git" and d.code.value == "stage-failed" for d in result.stats.degradations)
    _assert_accounting(result)
