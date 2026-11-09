"""分析流水线：把 采集 → 指标 → 评分 → 排序 → 目录聚合 编排为一次运行。"""

from __future__ import annotations

import fnmatch
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from githotmap.config.config import COMPOSITE_WEIGHTS, ScoringConfig
from githotmap.core.diagnostics import AnalysisStats, Degradation, DegradationCode, AnalysisDegradedError
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


@contextmanager
def _guard(stage: str, stats: AnalysisStats):
    """捕获阶段异常并记录统计信息，防止静默失败。"""
    start = time.perf_counter()
    try:
        yield
    except Exception as e:
        stats.degradations.append(Degradation(
            stage=stage,
            code=DegradationCode.STAGE_FAILED,
            path=None,
            summary=f"{stage} stage failed",
            detail=str(e)
        ))
    finally:
        stats.stage_elapsed_ms[stage] = (time.perf_counter() - start) * 1000.0


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
        stats = AnalysisStats()

        # 1. 采集
        with _guard("git", stats):
            records = self.history.collect(repo_path, since=since or cfg.since)
            stats.commits_seen = len(records)

        # 2. 指标聚合
        with _guard("metrics", stats):
            metrics_map = aggregate_file_metrics(
                records,
                recent_window_days=cfg.recent_window_days,
                decay_half_life_days=cfg.decay_half_life_days,
            )
            enrich_worktree_attributes(metrics_map, repo_path)
            stats.files_matched = len(metrics_map)

        # 2.5 结构信号
        scan = None
        with _guard("scanner", stats):
            scan_cfg = ScanConfig(exclude_patterns=list(cfg.exclude))
            scan = scan_repository(repo_path, config=scan_cfg)
            struct_by_path = scan.by_path()
            for path, m in metrics_map.items():
                struct = struct_by_path.get(path)
                if struct is not None:
                    m.max_cyclomatic_complexity = float(struct.max_cyclomatic_complexity)
                    m.max_nesting_depth = float(struct.max_nesting_depth)
                    m.symbol_count = float(struct.symbol_count)
                    m.import_count = float(len(struct.imports))

        # 2.6 SATD 信号（注意：如果 scanner 挂了，这里 scan 可能是 None，所以要判断）
        if scan is not None:
            with _guard("todo", stats):
                todo_scan = TodoDetector().detect(scan)
                todo_by_path: dict[str, int] = {}
                for item in todo_scan.todos:
                    todo_by_path[item.path] = todo_by_path.get(item.path, 0) + 1
                for path, m in metrics_map.items():
                    m.todo_count = float(todo_by_path.get(path, 0))

        # 3. 排除规则过滤
        if cfg.exclude:
            metrics_map = {
                path: m for path, m in metrics_map.items() if not _excluded(path, cfg.exclude)
            }

        # 3.5 自适应归一化
        caps_override: dict[str, float] = dict(cfg.normalization_caps)
        if cfg.enable_adaptive_caps and metrics_map:
            def _p90(values: list[float]) -> float:
                if not values: return 1.0
                s = sorted(values)
                idx = int(len(s) * 0.90)
                return max(s[idx], 1.0)

            caps_override.update({
                "commits": _p90([m.commits for m in metrics_map.values()]),
                "churn": _p90([m.churn for m in metrics_map.values()]),
                "loc": _p90([m.lines_of_code for m in metrics_map.values()]),
                "size_kb": _p90([m.size_bytes / 1024.0 for m in metrics_map.values()]),
            })

        # 4. 评分
        with _guard("scoring", stats):
            seed_mode = base_mode if base_mode is not None else ScoringMode.HOT
            scoring_cfg = replace(cfg, normalization_caps=caps_override)
            files: list[FileResult] = [score_file(m, seed_mode, scoring_cfg) for m in metrics_map.values()]

            # 把 scanner 里的限制信息合并到结果里
            if scan is not None:
                struct_by_path = scan.by_path()
                for f in files:
                    struct = struct_by_path.get(f.path)
                    if struct is not None and hasattr(struct, "limitations") and struct.limitations:
                        f.limitations.extend(struct.limitations)

            if composite is not None:
                weights = COMPOSITE_WEIGHTS.get(composite, [])
                for f in files:
                    apply_composite(f, composite, weights, thresholds=scoring_cfg.severity_thresholds)

            stats.files_emitted = len(files)

        # 5. 排序 & 6. 目录聚合
        ranked_files = rank_files(files, limit=limit if limit is not None else cfg.limit)
        folders = aggregate_folders(ranked_files)
        ranked_folders = rank_folders(folders, limit=limit if limit is not None else cfg.limit)

        # 7. 统计降级分布
        for d in stats.degradations:
            stats.degradations_by_code[d.code.value] = stats.degradations_by_code.get(d.code.value, 0) + 1
        stats.files_degraded = sum(1 for f in ranked_files if f.limitations) + len(stats.degradations)

        # 8. 严格模式拦截
        if cfg.degrade_policy == "strict" and (stats.degradations or stats.files_degraded > 0):
            raise AnalysisDegradedError(stats)

        return AnalysisResult(
            repo_path=str(repo_path),
            repo_urn=resolve_urn(repo_path),
            mode=(composite.value if composite is not None else seed_mode.value),
            files=ranked_files,
            folders=ranked_folders,
            stats=stats,  # 注入统计！
        )