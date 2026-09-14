"""HTML 渲染器的单元测试。"""

from __future__ import annotations

from githotmap.core.models import AnalysisResult, FileMetrics, FileResult, ScoringMode
from githotmap.renderers import registry


def _result() -> AnalysisResult:
    f = FileResult(
        metrics=FileMetrics(
            path="src/main.py",
            size_bytes=1000,
            lines_of_code=120.0,
            commits=30.0,
            churn=400.0,
            unique_contributors=3.0,
        ),
        mode_score=75.0,
        scores={ScoringMode.HOT.value: 75.0},
        reasoning={ScoringMode.HOT.value: ["High Churn"]},
    )
    return AnalysisResult(
        repo_path=".", repo_urn="local:test", mode="hot", files=[f]
    )


def test_html_is_registered() -> None:
    assert "html" in registry.available()


def test_html_render_is_self_contained_and_embeds_data() -> None:
    html = registry.render(_result(), "html")
    assert html.lstrip().startswith("<!doctype html>")
    assert "src/main.py" in html  # 数据已内嵌
    assert "scoreColor" in html  # 交互 JS 存在
    assert "cdn" not in html.lower()  # 无外部资源引用


def test_render_unknown_format_raises() -> None:
    import pytest

    with pytest.raises(KeyError):
        registry.render(_result(), "no-such-format")
