"""渲染层包：导入各渲染器实现以触发注册。"""

from __future__ import annotations

from githotmap.renderers import base, registry  # noqa: F401
from githotmap.renderers import html  # noqa: F401  导入即注册 html 渲染器

__all__ = ["base", "registry", "html"]
