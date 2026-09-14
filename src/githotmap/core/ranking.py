"""优先级排序与目录级聚合。"""

from __future__ import annotations

import posixpath
from collections import defaultdict
from typing import Iterable

from githotmap.core.models import FileResult, FolderResult


def rank_files(files: Iterable[FileResult], limit: int | None = None) -> list[FileResult]:
    """按 ``mode_score`` 降序排序；``limit`` 为 None 时返回全量。"""
    ranked = sorted(files, key=lambda f: f.mode_score, reverse=True)
    if limit is not None and len(ranked) > limit:
        return ranked[:limit]
    return ranked


def aggregate_folders(files: Iterable[FileResult]) -> list[FolderResult]:
    """把文件结果按父目录上卷（分数取均值，计数/改动量求和）。"""
    agg: dict[str, dict] = defaultdict(
        lambda: {"score": 0.0, "count": 0, "commits": 0.0, "churn": 0.0}
    )
    for f in files:
        folder = posixpath.dirname(f.path) or "."
        a = agg[folder]
        a["score"] += f.mode_score
        a["count"] += 1
        a["commits"] += f.commits
        a["churn"] += f.churn

    results = []
    for path, a in agg.items():
        results.append(
            FolderResult(
                path=path,
                score=a["score"] / a["count"],
                file_count=a["count"],
                total_commits=a["commits"],
                total_churn=a["churn"],
            )
        )
    return results


def rank_folders(folders: Iterable[FolderResult], limit: int | None = None) -> list[FolderResult]:
    """按目录评分降序排序；``limit`` 为 None 时返回全量。"""
    ranked = sorted(folders, key=lambda f: f.score, reverse=True)
    if limit is not None and len(ranked) > limit:
        return ranked[:limit]
    return ranked
