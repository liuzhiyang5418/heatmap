"""分析流水线：把 采集 → 指标 → 评分 → 排序 → 目录聚合 编排为一次运行。"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable

from githotmap.config.config import COMPOSITE_WEIGHTS, ScoringConfig
from githotmap.core.git import GitHistory, resolve_urn
from githotmap.core.metrics import aggregate_file_metrics, enrich_worktree_attributes
from githotmap.core.models import (
    AnalysisResult,
    CompositeMode,
    FileResult,
    ScoringMode,
)
from githotmap.core.ranking import aggregate_folders, rank_files, rank_folders
from githotmap.core.scoring import apply_composite, score_file


def _resolve_mode(mode: str | ScoringMode | CompositeMode) -> tuple[ScoringMode | None, CompositeMode | None]:
    """把用户输入解析为基础模式或复合模式。"""
    if isinstance(mode, CompositeMode):
        return None, mode
    if isinstance(mode, ScoringMode):
        return mode, None
    text = str(mode).strip().lower()
    for cls in (ScoringMode, CompositeMode):
        try:
            parsed = cls(text)
        except ValueError:
            continue
        if isinstance(parsed, ScoringMode):
            return parsed, None
        return None, parsed
    raise ValueError(f"未知评分模式 {mode!r}")


def _excluded(path: str, patterns: Iterable[str]) -> bool:
    """判断路径是否命中排除规则（支持递归通配 ``**/dir/``）。"""
    for pattern in patterns:
        pattern = pattern.strip()
        if not pattern:
            continue
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.endswith("/"):
            segment = pattern.rstrip("/")
            if segment in path.split("/"):
                return True
    return False


class AnalysisPipeline:
    """高层分析门面：默认零配置即可对仓库运行一次完整分析。"""

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig()
        self.history = GitHistory()

    def run(
        self,
        repo_path: str | Path,
        mode: str | ScoringMode | CompositeMode | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> AnalysisResult:
        """对 ``repo_path`` 运行完整分析并返回 :class:`AnalysisResult`。"""
        base_mode, composite = _resolve_mode(mode if mode is not None else self.config.mode)
        cfg = self.config

        # 1. 采集：单次遍历 git log。
        records = self.history.collect(repo_path, since=since or cfg.since)

        # 2. 指标聚合 + 工作区属性补充。
        metrics_map = aggregate_file_metrics(
            records,
            recent_window_days=cfg.recent_window_days,
            decay_half_life_days=cfg.decay_half_life_days,
        )
        enrich_worktree_attributes(metrics_map, repo_path)

        # 3. 排除规则过滤。
        if cfg.exclude:
            metrics_map = {
                path: m for path, m in metrics_map.items() if not _excluded(path, cfg.exclude)
            }

        # 4. 评分（始终计算全部基础模式）。
        #    复合模式需要一个基础模式作为初始 mode_score，随后被复合分数覆盖。
        seed_mode = base_mode if base_mode is not None else ScoringMode.HOT
        files: list[FileResult] = [
            score_file(m, seed_mode, cfg) for m in metrics_map.values()
        ]
        if composite is not None:
            blend = COMPOSITE_WEIGHTS[composite]
            for f in files:
                apply_composite(f, composite, blend)

        # 5. 排序与目录聚合。
        ranked = rank_files(files, limit if limit is not None else cfg.limit)
        folders = rank_folders(aggregate_folders(ranked))

        active_mode = (composite.value if composite is not None else seed_mode.value)
        return AnalysisResult(
            repo_path=str(repo_path),
            repo_urn=resolve_urn(repo_path),
            mode=active_mode,
            files=ranked,
            folders=folders,
        )
