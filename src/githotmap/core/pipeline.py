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
from githotmap.scanner import ScanConfig, scan_repository
from githotmap.todo import TodoDetector


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

        # 2.5 结构信号补充：打通 scanner 产出，以路径做字典 join。
        scan_cfg = ScanConfig(exclude_patterns=list(cfg.exclude))
        try:
            scan = scan_repository(repo_path, config=scan_cfg)
            struct_by_path = scan.by_path()
            for path, m in metrics_map.items():
                struct = struct_by_path.get(path)
                if struct is not None:
                    m.max_cyclomatic_complexity = float(struct.max_cyclomatic_complexity)
                    m.max_nesting_depth = float(struct.max_nesting_depth)
                    m.symbol_count = float(struct.symbol_count)
                    m.import_count = float(len(struct.imports))
        except Exception:
            # scanner 失败不阻断主流程：结构信号回退为默认值 0
            pass

        # 2.6 SATD 信号补充：打通 todo 模块产出，以路径做字典 join。
        try:
            todo_scan = TodoDetector().detect(scan)
            todo_by_path: dict[str, int] = {}
            for item in todo_scan.todos:
                todo_by_path[item.path] = todo_by_path.get(item.path, 0) + 1
            for path, m in metrics_map.items():
                m.todo_count = float(todo_by_path.get(path, 0))
        except Exception:
            # todo 检测失败不阻断主流程：SATD 信号回退为默认值 0
            pass

        # 3. 排除规则过滤。
        if cfg.exclude:
            metrics_map = {
                path: m for path, m in metrics_map.items() if not _excluded(path, cfg.exclude)
            }

        # 3.5 自适应归一化上限：按仓库内 p90 统计动态调整 caps，避免大仓库批量饱和。
        caps_override: dict[str, float] = dict(cfg.normalization_caps)
        if cfg.enable_adaptive_caps and metrics_map:
            def _p90(values: list[float]) -> float:
                if not values:
                    return 1.0
                s = sorted(values)
                idx = int(len(s) * 0.90)
                return max(s[idx], 1.0)

            commits_vals = [m.commits for m in metrics_map.values()]
            churn_vals = [m.churn for m in metrics_map.values()]
            loc_vals = [m.lines_of_code for m in metrics_map.values()]
            size_vals = [m.size_bytes / 1024.0 for m in metrics_map.values()]

            caps_override.update({
                "commits": _p90(commits_vals),
                "churn": _p90(churn_vals),
                "loc": _p90(loc_vals),
                "size_kb": _p90(size_vals),
            })

        # 4. 评分（始终计算全部基础模式）。
        #    复合模式需要一个基础模式作为初始 mode_score，随后被复合分数覆盖。
        seed_mode = base_mode if base_mode is not None else ScoringMode.HOT
        # 将自适应 caps 注入 config 的临时副本（避免污染原始配置）
        from dataclasses import replace
        scoring_cfg = replace(cfg, normalization_caps=caps_override)
        files: list[FileResult] = [
            score_file(m, seed_mode, scoring_cfg) for m in metrics_map.values()
        ]

        # 4.1 若用户选择复合模式，重新计算并覆盖 mode_score。
        if composite is not None:
            weights = COMPOSITE_WEIGHTS.get(composite, [])
            for f in files:
                apply_composite(f, weights)

        # 5. 排序：按 mode_score 取前 N。
        ranked_files = rank_files(files, limit=limit if limit is not None else cfg.limit)

        # 6. 目录聚合。
        folders = aggregate_folders(ranked_files)
        ranked_folders = rank_folders(folders, limit=limit if limit is not None else cfg.limit)

        return AnalysisResult(
            repo_path=str(repo_path),
            repo_urn=resolve_urn(repo_path),
            mode=(composite.value if composite is not None else seed_mode.value),
            files=ranked_files,
            folders=ranked_folders,
        )
