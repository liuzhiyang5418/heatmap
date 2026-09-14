"""指标聚合层：把原始 :class:`~githotmap.core.git.CommitRecord` 流聚合成文件级指标。

包含：

- :func:`gini` —— 贡献者集中度（公交因子信号）；
- :func:`decay_weight` —— 指数衰减权重（180 天半衰期，突出近期活跃）；
- :func:`aggregate_file_metrics` —— 按文件聚合 commits/churn/贡献者/年龄/近因衰减；
- :func:`enrich_worktree_attributes` —— 从工作区补充文件大小与行数（LOC）。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from githotmap.core.git import CommitRecord
from githotmap.core.models import FileMetrics

DEFAULT_RECENT_WINDOW_DAYS = 90.0
DECAY_HALF_LIFE_DAYS = 180.0
_SECONDS_PER_DAY = 86400.0


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """把 ``value`` 收敛到 [low, high]。"""
    if value < low:
        return low
    if value > high:
        return high
    return value


def gini(values: Iterable[float]) -> float:
    """计算基尼系数，衡量分布的均匀程度（0 = 完全均匀，1 = 完全集中）。"""
    vals = sorted(float(v) for v in values)
    n = len(vals)
    if n <= 1:
        return 0.0
    total = sum(vals)
    if total == 0:
        return 0.0
    weighted = sum((i + 1) * v for i, v in enumerate(vals))
    g = (2.0 * weighted) / (n * total) - (n + 1) / n
    return clamp(g)


def decay_weight(days_old: float, half_life_days: float = DECAY_HALF_LIFE_DAYS) -> float:
    """指数衰减权重：``0.5 ** (days_old / half_life)``，越旧权重越低。"""
    if days_old < 0:
        days_old = 0.0
    return 0.5 ** (days_old / half_life_days)


def aggregate_file_metrics(
    records: Iterable[CommitRecord],
    now: float | None = None,
    recent_window_days: float = DEFAULT_RECENT_WINDOW_DAYS,
    decay_half_life_days: float = DECAY_HALF_LIFE_DAYS,
) -> dict[str, FileMetrics]:
    """按文件聚合提交记录，返回 ``{path: FileMetrics}``。

    ``now`` 为参考时间戳（unix 秒），默认取当前时间；单元测试可注入固定值。
    """
    import time

    if now is None:
        now = time.time()

    # 中间聚合结构
    per_file: dict[str, dict] = {}
    for rec in records:
        entry = per_file.setdefault(
            rec.file_path,
            {
                "commits": 0.0,
                "churn": 0.0,
                "recent_commits": 0.0,
                "recent_churn": 0.0,
                "decayed_commits": 0.0,
                "decayed_churn": 0.0,
                "contributors": defaultdict(float),
                "first_ts": rec.timestamp,
            },
        )
        entry["commits"] += 1.0
        entry["churn"] += float(rec.churn)
        entry["contributors"][rec.author] += 1.0
        if rec.timestamp < entry["first_ts"]:
            entry["first_ts"] = rec.timestamp

        days_old = (now - rec.timestamp) / _SECONDS_PER_DAY
        weight = decay_weight(days_old, decay_half_life_days)
        entry["decayed_commits"] += weight
        entry["decayed_churn"] += float(rec.churn) * weight

        if rec.timestamp >= now - recent_window_days * _SECONDS_PER_DAY:
            entry["recent_commits"] += 1.0
            entry["recent_churn"] += float(rec.churn)

    result: dict[str, FileMetrics] = {}
    for path, e in per_file.items():
        contributors: dict[str, float] = dict(e["contributors"])
        result[path] = FileMetrics(
            path=path,
            commits=e["commits"],
            churn=e["churn"],
            recent_commits=e["recent_commits"],
            recent_churn=e["recent_churn"],
            unique_contributors=float(len(contributors)),
            age_days=(now - e["first_ts"]) / _SECONDS_PER_DAY,
            gini=gini(contributors.values()),
            decayed_commits=e["decayed_commits"],
            decayed_churn=e["decayed_churn"],
            contributor_commits=contributors,
        )
    return result


def _is_text_file(path: Path) -> bool:
    """粗判文件是否可读为文本（避免对二进制统计 LOC）。"""
    try:
        with path.open("rb") as fh:
            head = fh.read(1024)
    except OSError:
        return False
    return b"\x00" not in head


def count_lines(path: Path) -> float:
    """统计文本文件总行数；不可读或二进制返回 0。"""
    if not path.is_file() or not _is_text_file(path):
        return 0.0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return float(sum(1 for _ in fh))
    except OSError:
        return 0.0


def enrich_worktree_attributes(
    metrics_map: Mapping[str, FileMetrics], repo_root: str | Path
) -> None:
    """原地补充每个文件的 ``size_bytes`` 与 ``lines_of_code``（基于工作区当前状态）。"""
    root = Path(repo_root)
    for path, m in metrics_map.items():
        candidate = root / path
        try:
            m.size_bytes = candidate.stat().st_size
        except OSError:
            m.size_bytes = 0
        m.lines_of_code = count_lines(candidate)
