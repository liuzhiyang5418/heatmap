"""插件协议（预留扩展点）。

当前为底层框架：核心流程本身不加载插件，但预留了与流水线解耦的 hook 接口，
供后续 Sprint 引入 JIRA/Slack 等"模糊信号"注入或自定义后处理时使用。
"""

from __future__ import annotations

from abc import ABC
from typing import Any

from githotmap.core.models import AnalysisResult


class Plugin(ABC):
    """插件基类：在分析生命周期挂载自定义行为。"""

    #: 插件唯一名称。
    name: str = ""

    def on_analysis_start(self, context: dict[str, Any]) -> None:
        """分析开始前调用，``context`` 含 ``repo_path``、``config`` 等。"""

    def on_analysis_end(self, context: dict[str, Any], result: AnalysisResult) -> None:
        """分析结束后调用，可原地修改 ``result``。"""


class PluginManager:
    """极简插件管理器：按名称注册并分发生命周期事件。"""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def emit_start(self, context: dict[str, Any]) -> None:
        for plugin in self._plugins.values():
            plugin.on_analysis_start(context)

    def emit_end(self, context: dict[str, Any], result: AnalysisResult) -> None:
        for plugin in self._plugins.values():
            plugin.on_analysis_end(context, result)
