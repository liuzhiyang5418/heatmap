"""指标聚合层的单元测试。"""

from __future__ import annotations

from githotmap.core.git import CommitRecord
from githotmap.core.metrics import (
    aggregate_file_metrics,
    clamp,
    decay_weight,
    gini,
)

DAY = 86400
NOW = 1_000_000_000


def test_clamp() -> None:
    assert clamp(1.5) == 1.0
    assert clamp(-0.5) == 0.0
    assert clamp(0.4) == 0.4


def test_gini_bounds() -> None:
    assert gini([]) == 0.0
    assert gini([5]) == 0.0
    assert gini([1, 1, 1, 1]) == 0.0
    concentrated = gini([0, 0, 0, 10])
    assert concentrated == 0.75  # (2*40)/(4*10) - 5/4 = 0.75


def test_decay_weight() -> None:
    assert decay_weight(0.0) == 1.0
    assert decay_weight(180.0) == 0.5
    assert decay_weight(360.0) == 0.25


def test_aggregate_metrics() -> None:
    records = [
        CommitRecord("alice", NOW - 1 * DAY, "a.py", 10, 2),
        CommitRecord("alice", NOW - 10 * DAY, "a.py", 5, 0),
        CommitRecord("bob", NOW - 200 * DAY, "b.py", 1, 1),
    ]
    metrics = aggregate_file_metrics(records, now=NOW, recent_window_days=90.0)

    a = metrics["a.py"]
    assert a.commits == 2
    assert a.churn == 17.0
    assert a.unique_contributors == 1.0
    assert a.recent_commits == 2.0  # 1 天前与 10 天前均在 90 天近因窗口内
    assert a.recent_churn == 17.0
    assert a.gini == 0.0  # 单一贡献者

    b = metrics["b.py"]
    assert b.recent_commits == 0.0  # 200 天前不在近因窗口
    assert b.age_days == 200.0
