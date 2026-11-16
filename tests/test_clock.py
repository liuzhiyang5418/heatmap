"""时钟注入测试（NFR-3.1 双跑一致 / NFR-3.5 非确定字段收敛）。

锁定三件事：

1. ``FixedClock`` 让 ``analyzed_at`` / ``scanned_at`` / ``age_days`` 完全可复现；
2. 时间来源在整仓范围内只允许出现在 ``githotmap/clock.py``，
   避免有人随手写 ``datetime.now()`` 又把可复现性弄丢；
3. 不注入时行为不变（``SystemClock`` 兜底），保证向后兼容。
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from githotmap.clock import FixedClock, SystemClock
from githotmap.core.pipeline import AnalysisPipeline
from githotmap.scanner import scan_repository

_FIXED_INSTANT = datetime(2026, 1, 1, tzinfo=timezone.utc)
_FIXED_ISO = "2026-01-01T00:00:00+00:00"


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={**os.environ, **(env or {})},
    )


def _make_repo(root: Path) -> Path:
    """建一个提交时间固定为 2025-01-01 的仓库，使 age_days 可预测。"""
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-q",
        "-m",
        "fixture",
        env={
            "GIT_AUTHOR_DATE": "2025-01-01T00:00:00 +0000",
            "GIT_COMMITTER_DATE": "2025-01-01T00:00:00 +0000",
        },
    )
    return repo


# --------------------------------------------------------------------------- #
# 时钟实现本身
# --------------------------------------------------------------------------- #
def test_system_clock_now_is_utc_aware() -> None:
    now = SystemClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_fixed_clock_now_is_constant() -> None:
    clock = FixedClock(_FIXED_INSTANT)

    assert clock.now() == clock.now() == _FIXED_INSTANT


def test_fixed_clock_monotonic_steps_by_configuration() -> None:
    clock = FixedClock(_FIXED_INSTANT, step_seconds=0.5)

    assert clock.monotonic() == pytest.approx(0.0)
    assert clock.monotonic() == pytest.approx(0.5)
    assert clock.monotonic() == pytest.approx(1.0)


def test_fixed_clock_default_step_makes_elapsed_zero() -> None:
    clock = FixedClock(_FIXED_INSTANT)

    assert clock.monotonic() == clock.monotonic() == 0.0


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="时区"):
        FixedClock(datetime(2026, 1, 1))


def test_fixed_clock_rejects_negative_step() -> None:
    with pytest.raises(ValueError, match="不能为负"):
        FixedClock(_FIXED_INSTANT, step_seconds=-1.0)


# --------------------------------------------------------------------------- #
# 流水线注入
# --------------------------------------------------------------------------- #
def test_pipeline_uses_injected_clock_for_analyzed_at(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = AnalysisPipeline(clock=FixedClock(_FIXED_INSTANT)).run(repo)

    assert result.analyzed_at == _FIXED_ISO


def test_pipeline_double_run_is_identical_under_fixed_clock(tmp_path: Path) -> None:
    """同一 FixedClock 双跑，时间相关的输出必须完全一致（NFR-3.1）。"""
    repo = _make_repo(tmp_path)

    first = AnalysisPipeline(clock=FixedClock(_FIXED_INSTANT)).run(repo)
    second = AnalysisPipeline(clock=FixedClock(_FIXED_INSTANT)).run(repo)

    assert first.analyzed_at == second.analyzed_at
    assert [f.metrics.age_days for f in first.files] == [
        f.metrics.age_days for f in second.files
    ]
    assert [f.mode_score for f in first.files] == [f.mode_score for f in second.files]


def test_fixed_clock_pins_age_days(tmp_path: Path) -> None:
    """age_days 必须由注入时钟决定，而不是跑测试的当天。"""
    repo = _make_repo(tmp_path)

    result = AnalysisPipeline(clock=FixedClock(_FIXED_INSTANT)).run(repo)

    assert result.files
    # 提交时间固定为 2025-01-01，参考时刻 2026-01-01 → 365 天
    assert result.files[0].metrics.age_days == pytest.approx(365.0, abs=1.0)


def test_age_days_follows_the_injected_clock(tmp_path: Path) -> None:
    """换一个参考时刻，age_days 应随之改变——证明注入真的生效了。"""
    repo = _make_repo(tmp_path)
    later = _FIXED_INSTANT + timedelta(days=30)

    base = AnalysisPipeline(clock=FixedClock(_FIXED_INSTANT)).run(repo)
    shifted = AnalysisPipeline(clock=FixedClock(later)).run(repo)

    assert shifted.files[0].metrics.age_days == pytest.approx(
        base.files[0].metrics.age_days + 30.0, abs=1.0
    )


def test_pipeline_stage_elapsed_is_zero_under_fixed_clock(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    result = AnalysisPipeline(clock=FixedClock(_FIXED_INSTANT)).run(repo)

    assert result.stats.stage_elapsed_ms
    assert set(result.stats.stage_elapsed_ms.values()) == {0.0}


# --------------------------------------------------------------------------- #
# 扫描器注入
# --------------------------------------------------------------------------- #
def test_scanner_uses_injected_clock(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    scan = scan_repository(repo, clock=FixedClock(_FIXED_INSTANT))

    assert scan.scanned_at == _FIXED_ISO
    assert scan.stats.elapsed_ms == 0.0


def test_scanner_without_clock_still_works(tmp_path: Path) -> None:
    """不注入时必须回退到 SystemClock，保持向后兼容。"""
    repo = _make_repo(tmp_path)

    scan = scan_repository(repo)

    assert scan.scanned_at
    assert scan.stats.elapsed_ms >= 0.0


# --------------------------------------------------------------------------- #
# 时间来源收敛（NFR-3.5）
# --------------------------------------------------------------------------- #
def test_time_sources_are_confined_to_clock_module() -> None:
    """全仓库只允许 clock.py 调用 datetime.now / perf_counter / time.time。"""
    src_root = Path(__file__).resolve().parent.parent / "src"
    clock_module = src_root / "githotmap" / "clock.py"
    tokens = ("datetime.now(", "time.perf_counter(", "time.time(")

    offenders: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        if path == clock_module:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in tokens:
            if token in text:
                offenders.append(f"{path.relative_to(src_root).as_posix()}: {token}")

    assert offenders == [], f"时间来源必须收敛到 clock.py，发现: {offenders}"
