"""M5 流水线降级统计与严格模式回归测试。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from githotmap.cli.main import main
from githotmap.config.config import ScoringConfig
from githotmap.core.diagnostics import AnalysisDegradedError
from githotmap.core.pipeline import AnalysisPipeline


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(root: Path, *, with_syntax_error: bool = True) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "active.py").write_text(
        "def active(value):\n    return value + 1\n\n"
        + "\n".join(f"VALUE_{index} = {index}" for index in range(20))
        + "\n",
        encoding="utf-8",
    )
    if with_syntax_error:
        (repo / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    return repo


def test_file_limitations_are_included_in_degradation_statistics(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = AnalysisPipeline().run(repo)

    assert result.stats.files_degraded == 1
    assert result.stats.degradations_by_code["syntax-error"] == 1
    assert [f.path for f in result.files if f.limitations] == ["broken.py"]


def test_limit_does_not_hide_degraded_files_from_statistics(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    complete = AnalysisPipeline().run(repo)
    limited = AnalysisPipeline().run(repo, limit=1)

    assert [f.path for f in limited.files] == ["active.py"]
    assert limited.stats.files_degraded == complete.stats.files_degraded == 1
    assert limited.stats.degradations_by_code == complete.stats.degradations_by_code


def test_strict_mode_rejects_degradation_outside_the_top_n(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    config = ScoringConfig(degrade_policy="strict", limit=1)

    with pytest.raises(AnalysisDegradedError) as caught:
        AnalysisPipeline(config).run(repo)

    assert caught.value.stats.files_degraded == 1
    assert caught.value.stats.degradations_by_code["syntax-error"] == 1


def test_cli_strict_mode_reports_file_level_reason_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _make_repo(tmp_path)

    exit_code = main(
        [
            "analyze",
            "--repo-path",
            str(repo),
            "--strict",
            "--limit",
            "1",
            "--output",
            "json",
        ]
    )

    assert exit_code == 3
    assert "syntax-error" in capsys.readouterr().err


def test_strict_mode_accepts_a_clean_repository(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, with_syntax_error=False)
    config = ScoringConfig(degrade_policy="strict")

    result = AnalysisPipeline(config).run(repo)

    assert result.stats.files_degraded == 0
    assert result.stats.degradations_by_code == {}


def test_non_git_directory_degrades_without_uninitialized_variables(tmp_path: Path) -> None:
    plain_directory = tmp_path / "plain"
    plain_directory.mkdir()
    (plain_directory / "example.py").write_text("print('ok')\n", encoding="utf-8")

    result = AnalysisPipeline().run(plain_directory)

    assert result.files == []
    assert result.stats.files_degraded == 0
    assert result.stats.degradations_by_code == {"stage-failed": 1}

    with pytest.raises(AnalysisDegradedError):
        AnalysisPipeline(ScoringConfig(degrade_policy="strict")).run(plain_directory)


@pytest.mark.parametrize(
    ("target", "expected_stage"),
    [
        ("githotmap.core.pipeline.aggregate_file_metrics", "metrics"),
        ("githotmap.core.pipeline.score_file", "scoring"),
    ],
)
def test_stage_failures_do_not_escape_as_uninitialized_variable_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    expected_stage: str,
) -> None:
    repo = _make_repo(tmp_path, with_syntax_error=False)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(target, fail)
    result = AnalysisPipeline().run(repo)

    assert result.files == []
    assert [(d.stage, d.code.value) for d in result.stats.degradations] == [
        (expected_stage, "stage-failed")
    ]
    assert result.stats.degradations_by_code == {"stage-failed": 1}
