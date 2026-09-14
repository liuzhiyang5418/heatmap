"""渲染器抽象协议。

核心引擎只产出 :class:`~githotmap.core.models.AnalysisResult`；渲染层通过本协议
接入，实现"可插拔输出层"。新增输出格式只需实现 :class:`Renderer` 并注册。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from githotmap.core.models import AnalysisResult


class Renderer(ABC):
    """把分析结果渲染为字符串（HTML、SVG、JSON、文本等）的抽象基类。"""

    #: 渲染器唯一名称，注册表据此查找。
    name: str = ""

    @abstractmethod
    def render(self, result: AnalysisResult, **kwargs: Any) -> str:
        """渲染一个分析结果为最终字符串。"""
        raise NotImplementedError
