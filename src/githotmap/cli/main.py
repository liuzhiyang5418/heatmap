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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"githotmap {__version__}")
        return 0
    if args.command == "analyze":
        return _run_analyze(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
