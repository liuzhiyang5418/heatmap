"""排序与目录聚合的单元测试。"""

from __future__ import annotations

from githotmap.core.models import FileMetrics, FileResult, ScoringMode
from githotmap.core.ranking import aggregate_folders, rank_files, rank_folders


def _file(path: str, score: float, commits: float = 1.0, churn: float = 1.0) -> FileResult:
    return FileResult(
        metrics=FileMetrics(path=path, commits=commits, churn=churn),
        mode_score=score,
        scores={ScoringMode.HOT.value: score},
    )


def test_rank_files_descending_and_limit() -> None:
    files = [_file("a.py", 10), _file("b.py", 90), _file("c.py", 50)]
    ranked = rank_files(files)
    assert [f.path for f in ranked] == ["b.py", "c.py", "a.py"]
    assert [f.path for f in rank_files(files, limit=2)] == ["b.py", "c.py"]


def test_aggregate_folders_averages_scores() -> None:
    files = [
        _file("src/a.py", 90, commits=5, churn=100),
        _file("src/b.py", 10, commits=1, churn=10),
        _file("tests/c.py", 40, commits=2, churn=20),
    ]
    folders = rank_folders(aggregate_folders(files))
    src = next(f for f in folders if f.path == "src")
    assert src.score == 50.0
    assert src.file_count == 2
    assert src.total_commits == 6.0
    assert src.total_churn == 110.0
    # src 分数高于 tests，应排前
    assert folders[0].path == "src"
