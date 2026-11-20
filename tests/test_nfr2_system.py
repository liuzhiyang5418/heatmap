"""End-to-end checks for NFR-2 reporting on controlled repositories."""

import shutil
import subprocess
from pathlib import Path

import git
import pytest

from githotmap.config.config import ScoringConfig
from githotmap.core.diagnostics import AnalysisDegradedError
from githotmap.core.pipeline import AnalysisPipeline
from githotmap.renderers import registry


def _repository(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir()
    with git.Repo.init(root) as repo:
        for name, contents in files.items():
            (root / name).write_bytes(contents)
        repo.index.add(list(files))
        actor = git.Actor("Fixture", "fixture@example.invalid")
        repo.index.commit("add fixtures", author=actor, committer=actor)
    return root


@pytest.mark.parametrize(
    ("contents", "expected_code"),
    [
        (b"def invalid(:\n", "syntax-error"),
        (b"\x00binary data", "not-text"),
        (b"#" * 2_000_001, "too-large"),
    ],
    # 显式 id：第三个用例的内容是 200 万字符，pytest 默认会用参数值生成 id，
    # 在 Windows 上会撞到环境变量 32767 字符上限（Linux CI 不会暴露）。
    ids=["syntax-error", "not-text", "too-large"],
)
def test_real_file_limitations_survive_the_complete_pipeline(
    tmp_path: Path, contents: bytes, expected_code: str,
) -> None:
    repo = _repository(tmp_path / "repo", {"sample.py": contents})
    result = AnalysisPipeline().run(repo)

    assert [item.path for item in result.files] == ["sample.py"]
    assert expected_code in result.files[0].limitations
    assert result.stats.files_degraded == 1
    assert result.stats.degradations_by_code[expected_code] == 1
    with pytest.raises(AnalysisDegradedError) as caught:
        AnalysisPipeline(ScoringConfig(degrade_policy="strict")).run(repo)
    assert caught.value.stats.degradations_by_code[expected_code] == 1


@pytest.mark.parametrize(
    ("target", "stage"),
    [
        ("githotmap.core.pipeline.scan_repository", "scanner"),
        ("githotmap.core.pipeline.TodoDetector.detect", "todo"),
    ],
)
def test_injected_stage_failures_are_recorded_and_strict_mode_rejects_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, stage: str,
) -> None:
    repo = _repository(tmp_path / "repo", {"sample.py": b"print('ok')\n"})

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("injected failure")

    monkeypatch.setattr(target, fail)
    result = AnalysisPipeline().run(repo)
    assert [(item.stage, item.code.value) for item in result.stats.degradations] == [
        (stage, "stage-failed")
    ]
    assert result.stats.degradations_by_code == {"stage-failed": 1}
    with pytest.raises(AnalysisDegradedError):
        AnalysisPipeline(ScoringConfig(degrade_policy="strict")).run(repo)


def test_non_ascii_file_identity_survives_git_and_scanner(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", {"分析.py": b"print('ok')\n"})
    result = AnalysisPipeline().run(repo)
    assert [item.path for item in result.files] == ["分析.py"]
    assert result.stats.degradations == []


def test_unreadable_scanner_input_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repository(tmp_path / "repo", {"sample.py": b"print('ok')\n"})
    original = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path.name == "sample.py":
            raise PermissionError("injected read failure")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    result = AnalysisPipeline().run(repo)
    assert result.files[0].limitations == ["unreadable"]
    assert result.stats.degradations_by_code["unreadable"] == 1
    with pytest.raises(AnalysisDegradedError):
        AnalysisPipeline(ScoringConfig(degrade_policy="strict")).run(repo)


def test_tracked_symbolic_link_is_reported(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", {"target.py": b"print('ok')\n"})
    link = repo / "linked.py"
    try:
        link.symlink_to("target.py")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")
    with git.Repo(repo) as repository:
        repository.git.add("linked.py")
        actor = git.Actor("Fixture", "fixture@example.invalid")
        repository.index.commit("add link", author=actor, committer=actor)

    result = AnalysisPipeline().run(repo)
    linked = next(item for item in result.files if item.path == "linked.py")
    assert linked.limitations == ["symlink"]
    assert result.stats.degradations_by_code["symlink"] == 1
    with pytest.raises(AnalysisDegradedError):
        AnalysisPipeline(ScoringConfig(degrade_policy="strict")).run(repo)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_html_keeps_hidden_file_reason_counts(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", {
        "valid.py": b"print('ok')\n",
        "broken.py": b"def broken(:\n",
    })
    result = AnalysisPipeline().run(repo, limit=0)
    page = tmp_path / "limited.html"
    page.write_text(registry.render(result, "html"), encoding="utf-8")
    completed = subprocess.run(
        [shutil.which("node"), str(Path(__file__).with_name("html_interactions.js")), str(page), "limited"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
