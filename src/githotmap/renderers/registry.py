"""渲染器注册表：按名称注册/查找渲染器，实现输出格式的热插拔。"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from githotmap.core.models import AnalysisResult
from githotmap.renderers.base import Renderer

_R = TypeVar("_R", bound=type[Renderer])

_registry: dict[str, type[Renderer]] = {}


def register(name: str | None = None) -> Callable[[_R], _R]:
    """类装饰器：把渲染器类登记到注册表。"""

    def decorator(cls: _R) -> _R:
        key = name or getattr(cls, "name", "") or cls.__name__
        _registry[key] = cls
        return cls

    return decorator


def get_renderer(name: str) -> type[Renderer]:
    """按名称查找渲染器类；未知名称抛出 :class:`KeyError`。"""
    try:
        return _registry[name]
    except KeyError:
        raise KeyError(
            f"未知渲染器 {name!r}，可用: {sorted(_registry)}"
        ) from None


def render(result: AnalysisResult, name: str = "html", **kwargs: Any) -> str:
    """按名称渲染结果（默认 html）。"""
    return get_renderer(name)().render(result, **kwargs)


def available() -> list[str]:
    """返回已注册的渲染器名称。"""
    return sorted(_registry)
