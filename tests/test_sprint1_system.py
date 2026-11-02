"""Small, controlled end-to-end fixtures for the Sprint 1 report path."""

import json
from pathlib import Path

import git
import pytest

from githotmap.cli.main import main


@pytest.mark.parametrize("content", [
    "def add(a, b):\n    return a + b\n",
    "# TODO: review boundary\ndef classify(x):\n    if x > 0:\n        return 1\n    return 0\n",
])
def test_cli_analyzes_controlled_repositories_to_json_and_html(tmp_path: Path, content: str) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    repo = git.Repo.init(worktree)
    source = worktree / "sample.py"
    source.write_text(content, encoding="utf-8")
    repo.index.add([source.name])
    actor = git.Actor("Test", "test@example.invalid")
    repo.index.commit("fixture", author=actor, committer=actor,
                      author_date="2026-01-01T12:00:00+0000", commit_date="2026-01-01T12:00:00+0000")
    try:
        report_json = tmp_path / "report.json"
        report_html = tmp_path / "report.html"
        assert main(["analyze", "--repo-path", str(worktree), "--mode", "complexity",
                     "--output", "json", "--output-file", str(report_json)]) == 0
        data = json.loads(report_json.read_text(encoding="utf-8"))
        assert data["mode"] == "complexity"
        assert [file["path"] for file in data["files"]] == ["sample.py"]
        assert data["files"][0]["metrics"]["commits"] == 1
        assert "breakdowns" in data["files"][0]
        assert main(["analyze", "--repo-path", str(worktree), "--mode", "complexity",
                     "--output", "html", "--output-file", str(report_html)]) == 0
        assert "sample.py" in report_html.read_text(encoding="utf-8")
    finally:
        repo.close()


def test_web_analyzes_a_controlled_repository(tmp_path: Path) -> None:
    pytest.importorskip("flask")
    from githotmap.web.app import create_app

    worktree = tmp_path / "web-repo"
    worktree.mkdir()
    repo = git.Repo.init(worktree)
    (worktree / "web_example.py").write_text("print('ok')\n", encoding="utf-8")
    repo.index.add(["web_example.py"])
    actor = git.Actor("Test", "test@example.invalid")
    repo.index.commit("fixture", author=actor, committer=actor)
    try:
        client = create_app().test_client()
        assert client.get("/").status_code == 200
        with client.session_transaction() as session:
            csrf = session["csrf_token"]
        response = client.post("/analyze", data={"repo_path": str(worktree), "mode": "hot", "csrf_token": csrf})
        assert response.status_code == 200
        assert b"web_example.py" in response.data
    finally:
        repo.close()
