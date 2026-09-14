"""编程式调用示例：用合成数据演示 评分 → 排序 → 渲染 全链路。

无需真实 Git 仓库即可运行，产物为同目录下的 ``demo_heatmap.html``。

运行::

    python examples/demo.py
"""

from __future__ import annotations

from pathlib import Path

from githotmap.config.config import ScoringConfig
from githotmap.core.models import AnalysisResult, FileMetrics, ScoringMode
from githotmap.core.ranking import rank_files
from githotmap.core.scoring import score_files
from githotmap.renderers import registry


def _synthetic_files() -> list[FileMetrics]:
    return [
        FileMetrics(
            path="src/parser.py", size_bytes=24000, lines_of_code=980.0, commits=220.0,
            churn=4400.0, recent_commits=48.0, recent_churn=980.0, unique_contributors=3.0,
            age_days=810.0, gini=0.72, decayed_commits=62.0, decayed_churn=1250.0,
        ),
        FileMetrics(
            path="src/utils.py", size_bytes=9000, lines_of_code=340.0, commits=90.0,
            churn=1200.0, recent_commits=6.0, recent_churn=90.0, unique_contributors=5.0,
            age_days=700.0, gini=0.35, decayed_commits=18.0, decayed_churn=260.0,
        ),
        FileMetrics(
            path="src/api/handlers.py", size_bytes=15000, lines_of_code=520.0, commits=140.0,
            churn=2100.0, recent_commits=30.0, recent_churn=640.0, unique_contributors=4.0,
            age_days=400.0, gini=0.48, decayed_commits=40.0, decayed_churn=760.0,
        ),
        FileMetrics(
            path="tests/test_parser.py", size_bytes=6000, lines_of_code=280.0, commits=60.0,
            churn=700.0, recent_commits=20.0, recent_churn=210.0, unique_contributors=2.0,
            age_days=300.0, gini=0.55, decayed_commits=24.0, decayed_churn=280.0,
        ),
    ]


def main() -> None:
    cfg = ScoringConfig(mode=ScoringMode.HOT)
    metrics = _synthetic_files()

    files = score_files(metrics, ScoringMode.HOT, cfg)
    ranked = rank_files(files, limit=10)

    result = AnalysisResult(
        repo_path="(synthetic)",
        repo_urn="local:demo",
        mode=ScoringMode.HOT.value,
        files=ranked,
    )
    html = registry.render(result, "html")
    out = Path(__file__).resolve().parent.parent / "demo_heatmap.html"
    out.write_text(html, encoding="utf-8")

    print(f"已生成 {out}")
    print(f"{'文件':<24} {'分数':>6}")
    for f in ranked:
        print(f"{f.path:<24} {f.mode_score:>6.1f}")


if __name__ == "__main__":
    main()
