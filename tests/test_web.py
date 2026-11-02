"""Tests for the optional local web entry point."""

from pathlib import Path

import pytest

pytest.importorskip("flask")

from githotmap.core.models import AnalysisResult
from githotmap.web.app import create_app


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def token(client) -> str:
    assert client.get("/").status_code == 200
    with client.session_transaction() as session:
        return session["csrf_token"]


def test_request_requires_form_token(client, tmp_path: Path) -> None:
    response = client.post("/analyze", data={"repo_path": str(tmp_path), "mode": "hot"})
    assert response.status_code == 403


def test_rejects_unexpected_host_header(client) -> None:
    assert client.get("/", headers={"Host": "external.example"}).status_code == 403


def test_invalid_path_and_mode_are_explained(client, tmp_path: Path) -> None:
    csrf = token(client)
    invalid = client.post("/analyze", data={"csrf_token": csrf, "repo_path": "<missing>", "mode": "hot"})
    assert invalid.status_code == 400
    assert b"Enter an existing local directory." in invalid.data
    assert b"&lt;missing&gt;" in invalid.data
    invalid_mode = client.post("/analyze", data={"csrf_token": csrf, "repo_path": str(tmp_path), "mode": "other"})
    assert invalid_mode.status_code == 400
    assert b"Select a valid scoring mode." in invalid_mode.data


def test_successful_request_uses_existing_pipeline_and_renderer(client, tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def run(self, repo_path, mode):
        captured.update(repo_path=repo_path, mode=mode)
        return AnalysisResult(repo_path=str(repo_path), repo_urn="local:test", mode=mode)

    monkeypatch.setattr("githotmap.web.app.AnalysisPipeline.run", run)
    response = client.post("/analyze", data={"csrf_token": token(client), "repo_path": str(tmp_path), "mode": "roi"})
    assert response.status_code == 200
    assert response.data.startswith(b"<!doctype html>")
    assert captured == {"repo_path": tmp_path, "mode": "roi"}


def test_pipeline_failure_is_shown_as_text(client, tmp_path: Path, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise ValueError("<invalid repository>")

    monkeypatch.setattr("githotmap.web.app.AnalysisPipeline.run", fail)
    response = client.post("/analyze", data={"csrf_token": token(client), "repo_path": str(tmp_path), "mode": "hot"})
    assert response.status_code == 422
    assert b"&lt;invalid repository&gt;" in response.data
