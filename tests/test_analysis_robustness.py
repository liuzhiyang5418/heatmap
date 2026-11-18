"""NFR-2/3 checks for Member 4's deep Git-history analysis APIs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import git
import pytest

from githotmap.cli.main import main
from githotmap.core.analysis import (
    branch_activity,
    branch_activity_with_degradations,
    commit_frequency_with_degradations,
    file_ownership_with_degradations,
    knowledge_islands_with_degradations,
    top_contributors,
    top_contributors_with_degradations,
)
from githotmap.core.git import CODE_EMPTY_REPO, CODE_SHALLOW_CLONE


def _make_shallow_repo(root: Path) -> Path:
    source = root / "source"
    repo = git.Repo.init(source)
    workdir = Path(repo.working_tree_dir or source)
    actor = git.Actor("Fixture", "fixture@example.invalid")
    for index in range(2):
        (workdir / "module.py").write_text(
            "\n".join(f"VALUE_{line} = {line}" for line in range(index + 1)) + "\n",
            encoding="utf-8",
        )
        repo.index.add(["module.py"])
        repo.index.commit(f"fixture {index}", author=actor, committer=actor)
    repo.close()

    shallow = root / "shallow"
    subprocess.run(
        ["git", "clone", "--depth", "1", source.as_uri(), str(shallow)],
        check=True,
        capture_output=True,
    )
    return shallow


def test_deep_analysis_apis_expose_shallow_history_diagnostics(tmp_path: Path) -> None:
    repo = _make_shallow_repo(tmp_path)
    outcomes = [
        top_contributors_with_degradations(repo),
        branch_activity_with_degradations(repo),
        knowledge_islands_with_degradations(repo),
        file_ownership_with_degradations(repo),
        commit_frequency_with_degradations(repo),
    ]

    for outcome in outcomes:
        assert outcome.result is not None
        assert len(outcome.degradations) == 1
        assert outcome.degradations[0].code == CODE_SHALLOW_CLONE
        assert len(outcome.degradations[0].path or "") == 40
        assert outcome.degradations[0].summary == (
            "history before this shallow boundary is unavailable"
        )


def test_deep_analysis_apis_expose_empty_repository_diagnostics(tmp_path: Path) -> None:
    repo_path = tmp_path / "empty"
    git.Repo.init(repo_path).close()
    outcomes = [
        top_contributors_with_degradations(repo_path),
        branch_activity_with_degradations(repo_path),
        knowledge_islands_with_degradations(repo_path),
        file_ownership_with_degradations(repo_path),
        commit_frequency_with_degradations(repo_path),
    ]

    for outcome in outcomes:
        assert len(outcome.degradations) == 1
        assert outcome.degradations[0].code == CODE_EMPTY_REPO
        assert outcome.degradations[0].path is None


def test_legacy_deep_analysis_warns_when_shallow_history_is_incomplete(
    tmp_path: Path,
) -> None:
    repo = _make_shallow_repo(tmp_path)

    with pytest.warns(RuntimeWarning, match="machine-readable reasons"):
        top_contributors(repo)
    with pytest.warns(RuntimeWarning, match="machine-readable reasons"):
        branch_activity(repo)


def test_deep_analysis_diagnostics_are_repeatable(tmp_path: Path) -> None:
    repo = _make_shallow_repo(tmp_path)

    first = top_contributors_with_degradations(repo)
    second = top_contributors_with_degradations(repo)

    assert first.result == second.result
    assert [item.to_dict() for item in first.degradations] == [
        item.to_dict() for item in second.degradations
    ]


def test_history_cli_reports_shallow_history_limitations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_shallow_repo(tmp_path)

    assert main(["history", "--repo-path", str(repo)]) == 0
    assert "shallow-clone" in capsys.readouterr().err
