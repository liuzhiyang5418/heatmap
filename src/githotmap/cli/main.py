"""命令行入口：``githotmap analyze`` / ``githotmap version``。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from githotmap import __version__
from githotmap.config.config import ScoringConfig
from githotmap.core.models import ScoringMode
from githotmap.core.pipeline import AnalysisPipeline
from githotmap.renderers import registry

_ALL_MODES = ["hot", "risk", "complexity", "roi", "active_owners", "refactor_now", "legacy_debt"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="githotmap",
        description="Git 技术债热力图与优先级排序工具：把 Git 历史转化为风险热力图。",
    )
    parser.add_argument("--version", action="store_true", help="显示版本号后退出")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    analyze = sub.add_parser("analyze", help="分析一个 Git 仓库并输出热力图")
    analyze.add_argument("--repo-path", default=".", help="Git 仓库路径（默认当前目录）")
    analyze.add_argument(
        "--mode",
        choices=_ALL_MODES,
        default=None,
        help="评分模式（含复合模式，默认 hot，可被 --preset 覆盖）",
    )
    analyze.add_argument(
        "--preset",
        choices=["small", "large", "infra"],
        help="仓库形状预设（覆盖默认阈值/模式/limit）",
    )
    analyze.add_argument(
        "--output",
        default="html",
        help=f"输出格式（已注册: {', '.join(registry.available())}，默认 html）",
    )
    analyze.add_argument("--output-file", help="输出文件路径（html 默认 heatmap.html）")
    analyze.add_argument("--limit", type=int, help="最多展示的文件数")
    analyze.add_argument("--since", help="仅分析该时间之后的提交（如 '1 year ago'）")
    analyze.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="排除路径模式，可重复（如 '**/node_modules/'）",
    )

    history = sub.add_parser("history", help="历史数据分析（贡献者/分支/知识孤岛）")
    history.add_argument("--repo-path", default=".", help="Git 仓库路径（默认当前目录）")
    history.add_argument("--since", help="仅统计该时间之后的提交（如 '30 days ago'）")
    history.add_argument(
        "--top-n", type=int, default=10, help="贡献者排名前 N 位（默认 10）"
    )
    history.add_argument(
        "--min-churn",
        type=int,
        default=0,
        help="知识孤岛的最小总改动量（过滤拼写修正等噪声，默认 0）",
    )
    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    try:
        if args.preset:
            config = ScoringConfig.from_preset(args.preset)
        else:
            config = ScoringConfig()
        if args.mode in _ALL_MODES[:4]:
            config.mode = ScoringMode(args.mode)
        config.exclude = list(args.exclude)
    except (KeyError, ValueError) as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    pipeline = AnalysisPipeline(config)
    try:
        result = pipeline.run(
            repo_path=args.repo_path,
            mode=args.mode,
            since=args.since,
            limit=args.limit,
        )
    except Exception as exc:  # noqa: BLE001 —— CLI 顶层兜底，给出可读错误
        print(f"分析失败: {exc}", file=sys.stderr)
        return 1

    try:
        rendered = registry.render(result, args.output)
    except KeyError as exc:
        print(f"{exc}", file=sys.stderr)
        return 2

    output_file = args.output_file
    if output_file is None and args.output == "html":
        output_file = "heatmap.html"
    if output_file:
        Path(output_file).write_text(rendered, encoding="utf-8")
        print(f"已写出: {output_file}（{len(result.files)} 个文件，模式 {result.mode}）")
    else:
        sys.stdout.write(rendered)
    return 0


def _run_history(args: argparse.Namespace) -> int:
    from githotmap.core.analysis import (
        branch_activity,
        commit_frequency,
        file_ownership,
        knowledge_islands,
        top_contributors,
    )

    repo_path = args.repo_path

    # ---- Top Contributors ----
    print("=" * 60)
    print(f"Top Contributors (churn 降序, top {args.top_n})")
    print("-" * 60)
    try:
        contributors = top_contributors(repo_path, top_n=args.top_n, since=args.since)
    except Exception as exc:
        print(f"采集失败: {exc}", file=sys.stderr)
        return 1
    if contributors:
        name_w = max(len(c.name) for c in contributors)
        print(f"{'Author':<{name_w}} {'Commits':>8} {'Added':>8} {'Deleted':>8} {'Churn':>8}")
        for c in contributors:
            print(f"{c.name:<{name_w}} {c.commits:>8.0f} {c.total_added:>8} {c.total_deleted:>8} {c.churn:>8}")
    else:
        print("(无数据)")

    # ---- Branch Activity ----
    print("\n" + "=" * 60)
    print("Branch Activity")
    print("-" * 60)
    try:
        branches = branch_activity(repo_path)
    except Exception as exc:
        print(f"采集失败: {exc}", file=sys.stderr)
        return 1
    if branches:
        for b in branches:
            print(f"  {b.name:<20} commits={b.commit_count:>5}  last={b.last_commit_datetime.strftime('%Y-%m-%d')}  by {b.last_author}")
            print(f"    {b.last_message[:80]}")
    else:
        print("(无数据)")

    # ---- Knowledge Islands ----
    print("\n" + "=" * 60)
    print(f"Knowledge Islands (only 1 contributor, min churn={args.min_churn})")
    print("-" * 60)
    try:
        islands = knowledge_islands(repo_path, min_churn=args.min_churn)
    except Exception as exc:
        print(f"采集失败: {exc}", file=sys.stderr)
        return 1
    if islands:
        for o in islands:
            churn = next(iter(o.contributors.values()))
            print(f"  {o.file_path}  →  {o.dominant_author}  (churn={churn})")
    else:
        print("(无知识孤岛)")

    # ---- Commit Frequency ----
    print("\n" + "=" * 60)
    print("Commit Frequency (by day)")
    print("-" * 60)
    try:
        freq = commit_frequency(repo_path, group_by="day", since=args.since)
    except Exception as exc:
        print(f"采集失败: {exc}", file=sys.stderr)
        return 1
    if freq.counts:
        print(f"  Total: {freq.total_commits} commits")
        for day, count in sorted(freq.counts.items(), reverse=True)[:14]:
            print(f"    {day}: {count}")
    else:
        print("(无数据)")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"githotmap {__version__}")
        return 0
    if args.command == "analyze":
        return _run_analyze(args)
    if args.command == "history":
        return _run_history(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
