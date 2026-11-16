"""可注入时钟：把「当前时刻」与「单调计时」从各处实现中抽出来。

为什么需要它（NFR-3 可复现性与可验证性）：

- ``analyzed_at`` / ``scanned_at`` / ``age_days`` / ``elapsed_ms`` 都依赖运行时刻，
  同一仓库换一天跑，结果就会变；
- 冻结夹具与指纹回归必须能**固定时钟**，否则每次跑出的 age 都不同，指纹永远对不上；
- 因此全仓库只允许本模块调用 ``datetime.now`` / ``time.perf_counter`` / ``time.time``，
  其余模块一律通过注入的 :class:`Clock` 取时间。

本模块位于包顶层而不是 ``core/`` 下，是为了让 ``scanner`` 也能安全使用：
``core`` 与 ``scanner`` 都依赖它，而它只依赖标准库，不会引入循环导入。

用法::

    from datetime import datetime, timezone
    from githotmap.clock import FixedClock, SystemClock

    pipeline = AnalysisPipeline(clock=FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)))
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Protocol

__all__ = ["Clock", "FixedClock", "SystemClock"]


class Clock(Protocol):
    """时间源协议：注入点只依赖这两个方法。

    实现不必继承本类（结构化类型），只要提供 ``now`` 与 ``monotonic`` 即可。
    """

    def now(self) -> datetime:
        """当前时刻；**必须带时区**，统一按 UTC 解释。"""
        ...

    def monotonic(self) -> float:
        """单调递增的秒数，用于测量耗时（不受系统时钟回拨影响）。"""
        ...


class SystemClock:
    """默认实现：真实系统时钟。"""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.perf_counter()


class FixedClock:
    """固定时钟：``now()`` 恒定，``monotonic()`` 按固定步进递增。

    - ``now()`` 恒定，使 ``analyzed_at`` / ``scanned_at`` / ``age_days`` 可复现；
    - ``monotonic()`` 默认步进 0，使 ``elapsed_ms`` 恒为 0、不污染指纹；
      需要模拟耗时时可传 ``step_seconds``。
    """

    __slots__ = ("_instant", "_step_seconds", "_ticks")

    def __init__(self, instant: datetime, step_seconds: float = 0.0) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock 需要带时区的 datetime（建议 timezone.utc）")
        if step_seconds < 0:
            raise ValueError("step_seconds 不能为负")
        self._instant = instant
        self._step_seconds = step_seconds
        self._ticks = 0

    def now(self) -> datetime:
        return self._instant

    def monotonic(self) -> float:
        value = self._ticks * self._step_seconds
        self._ticks += 1
        return value
