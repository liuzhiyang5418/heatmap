"""Machine-readable rendering of the existing analysis result."""

from __future__ import annotations

import json
from typing import Any

from githotmap.core.models import AnalysisResult
from githotmap.renderers.base import Renderer
from githotmap.renderers.registry import register


@register("json")
class JSONRenderer(Renderer):
    """Serialize the same result used by the HTML renderer."""

    name = "json"

    def render(self, result: AnalysisResult, **kwargs: Any) -> str:
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
