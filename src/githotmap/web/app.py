"""A small local interface over the existing analysis and HTML renderer."""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask, Response, abort, render_template_string, request, session

from githotmap.core.models import CompositeMode, ScoringMode
from githotmap.core.pipeline import AnalysisPipeline
from githotmap.renderers import registry

_MODES = tuple(mode.value for mode in ScoringMode) + tuple(mode.value for mode in CompositeMode)

_FORM = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Git 技术债热力图</title>
<style>
body{font:16px/1.6 system-ui,sans-serif;max-width:48rem;margin:3rem auto;padding:0 1rem;color:#202b38}
label{display:block;margin-top:1rem} input,select,button{font:inherit;padding:.5rem}
input{width:min(100%,40rem);box-sizing:border-box} button{margin-top:1.5rem;cursor:pointer}
.error{border-left:4px solid #b32929;padding:.5rem 1rem;background:#fff0f0}
</style></head><body>
<h1>Git 技术债热力图</h1>
<p>输入本机 Git 仓库路径，生成可离线查看的分析报告。分数是待人工复核的候选信号。</p>
{% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
<form action="{{ url_for('analyze') }}" method="post">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label for="repo_path">本机仓库路径</label>
<input id="repo_path" name="repo_path" value="{{ repo_path }}" required>
<label for="mode">评分模式</label><select id="mode" name="mode">
{% for item in modes %}<option value="{{ item }}"{% if item == mode %} selected{% endif %}>{{ item }}</option>{% endfor %}
</select><br><button type="submit">生成报告</button>
</form></body></html>"""


def create_app() -> Flask:
    """Create an app intended to be bound to loopback by the CLI."""
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")

    @app.before_request
    def require_local_host() -> None:
        if request.host.split(":", 1)[0].lower() not in {"localhost", "127.0.0.1"}:
            abort(403)

    def form(error: str = "", repo_path: str = "", mode: str = "hot", status: int = 200) -> Response:
        token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
        return Response(
            render_template_string(
                _FORM, error=error, repo_path=repo_path, mode=mode, modes=_MODES, csrf_token=token
            ),
            status=status,
            mimetype="text/html",
        )

    @app.get("/")
    def index() -> Response:
        return form()

    @app.post("/analyze")
    def analyze() -> Response:
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            return form("请求已过期，请重新打开页面再试。", status=403)

        repo_path = request.form.get("repo_path", "").strip()
        mode = request.form.get("mode", "hot")
        if not repo_path or not Path(repo_path).expanduser().is_dir():
            return form("请输入存在的本机目录。", repo_path, mode, 400)
        if mode not in _MODES:
            return form("请选择有效的评分模式。", repo_path, "hot", 400)
        try:
            result = AnalysisPipeline().run(repo_path=Path(repo_path).expanduser(), mode=mode)
        except Exception as exc:  # noqa: BLE001 - report unexpected pipeline errors in the UI
            return form(f"分析失败：{exc}", repo_path, mode, 422)
        return Response(registry.render(result, "html"), mimetype="text/html")

    return app
