"""从**固定快照**生成评估答案键（`docs/evaluation-contract.md` 的 T1 / T2 / T4）。

为什么必须由脚本生成：契约 §3 要求答案键「在任何一次会话之前、从冻结数据算出」。
人工一边看结果一边写答案，等于把目标往结果那边挪。

用法::

    # 1) 先把快照固定到某个提交（脚本会把该提交写进答案键）
    python examples/evaluation/build_answer_key.py \
        --repo . --data X --mode roi --out answer_key_X.json

    # 2) T3 是解释题，脚本只给出候选对象及其指标明细，答案仍需人工撰写
    python examples/evaluation/build_answer_key.py --repo . --data X --show-t3-candidates

契约对齐：本脚本只依赖 `AnalysisPipeline` 的公开结果，不读测试夹具、不读历史答案，
因此任何一次运行都能复现（配合 `--mode` 与 `--min-dir-files` 两个参数）。

注意：**快照未固定就不要生成答案键。** 脚本会把 `repo_head` 写进输出；若该字段为空
（非 Git 目录），答案键就不可比较。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from githotmap.core.models import FileResult
from githotmap.core.pipeline import AnalysisPipeline

#: T2 的最小目录规模：太小的目录比例不稳定（1/1 = 100%），按契约冻结为参数。
DEFAULT_MIN_DIR_FILES = 2

#: T2 「高分」的定义：该数据集分数的第 75 百分位（top 25%）。
#: 不用 severity ≥ high 是因为它依赖绝对阈值（50/100），小仓库上可能一个都够不到，
#: 会让 T2 无解——实测本仓库 roi 模式最高分仅 40 出头。分位数定义随数据集自适应，
#: 且实际阈值会写进答案键，保证可复现。
HIGH_SCORE_PERCENTILE = 0.75


def _high_score_threshold(scores: list[float], percentile: float = HIGH_SCORE_PERCENTILE) -> float:
    """数据集自适应的「高分」阈值（默认 top 25%）。"""
    if not scores:
        return 0.0
    ordered = sorted(scores)
    index = min(int(len(ordered) * percentile), len(ordered) - 1)
    return ordered[index]


def _head_commit(repo: Path) -> str | None:
    """读取快照对应的提交；非 Git 目录返回 None（答案键随后无法比较）。"""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _top_level_dir(path: str) -> str:
    """一级目录；根目录下的文件归到 '.'（与 T2 的答案键口径一致）。"""
    return path.split("/", 1)[0] if "/" in path else "."


def build_answer_key(repo: Path, data: str, mode: str, min_dir_files: int) -> dict[str, object]:
    """跑一次完整分析，产出 T1 / T2 / T4 的答案键与 T3 的候选。"""
    result = AnalysisPipeline().run(repo, mode=mode, limit=1_000_000)
    files: list[FileResult] = list(result.files)

    # ---- T1：分数最高的三个文件（同分按路径升序，规则冻结在答案键里）----
    ranked = sorted(files, key=lambda item: (-item.mode_score, item.path))
    top3 = [
        {"rank": index + 1, "path": item.path, "score": round(item.mode_score, 2)}
        for index, item in enumerate(ranked[:3])
    ]

    # ---- T2：一级目录中「高分文件 ÷ 可分析文件」最高的那个 ----
    threshold = _high_score_threshold([item.mode_score for item in files])
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "high": 0})
    for item in files:
        directory = _top_level_dir(item.path)
        buckets[directory]["total"] += 1
        if item.mode_score >= threshold:
            buckets[directory]["high"] += 1

    eligible = [
        {
            "directory": directory,
            "high": counts["high"],
            "total": counts["total"],
            "ratio": round(counts["high"] / counts["total"], 4),
        }
        for directory, counts in buckets.items()
        if counts["total"] >= min_dir_files
    ]
    eligible.sort(key=lambda row: (-row["ratio"], row["directory"]))

    # ---- T4：status == "missing" 的文件（缺失 ≠ 低风险）----
    missing = sorted(item.path for item in files if item.status == "missing")

    # ---- T3：解释题候选；给出指标明细，供人工撰写答案 ----
    candidates = [
        {
            "path": item.path,
            "rank": index + 1,
            "score": round(item.mode_score, 2),
            "severity": item.severities.get(mode, ""),
            "metrics": {
                "commits": int(item.metrics.commits),
                "churn": int(item.metrics.churn),
                "contributors": int(item.metrics.unique_contributors),
                "gini": round(item.metrics.gini, 3),
                "age_days": int(item.metrics.age_days),
                "lines_of_code": int(item.metrics.lines_of_code),
            },
            "reasoning": list(item.reasoning.get(mode, [])),
        }
        for index, item in enumerate(ranked[:5])
    ]

    return {
        "contract": "docs/evaluation-contract.md v1.0",
        "data": data,
        "mode": mode,
        "min_dir_files": min_dir_files,
        "high_score_threshold": round(threshold, 2),
        "high_score_rule": f"score >= dataset {HIGH_SCORE_PERCENTILE:.0%} percentile",
        "repo_head": _head_commit(repo),
        "file_count": len(files),
        "T1": {"rule": "score desc, path asc", "answer": top3},
        "T2": {
            "rule": "high/total desc, directory asc",
            "high_score_threshold": round(threshold, 2),
            "ranking": eligible[:10],
            "answer": eligible[0] if eligible else None,
        },
        "T3": {
            "note": "解释题需人工撰写答案：引用两项真实指标，并说明候选≠确诊",
            "candidates": candidates,
        },
        "T4": {"rule": "status == missing", "answer": missing},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成评估答案键（T1/T2/T4 + T3 候选）")
    parser.add_argument("--repo", default=".", help="快照仓库路径（默认当前目录）")
    parser.add_argument("--data", default="X", help="数据集标识（X / Y），写入答案键")
    parser.add_argument("--mode", default="roi", help="评分模式（默认 roi，与演示一致）")
    parser.add_argument(
        "--min-dir-files",
        type=int,
        default=DEFAULT_MIN_DIR_FILES,
        help=f"T2 的最小目录规模（默认 {DEFAULT_MIN_DIR_FILES}）",
    )
    parser.add_argument("--out", help="输出 JSON 路径；缺省打印到 stdout")
    parser.add_argument(
        "--show-t3-candidates",
        action="store_true",
        help="只打印 T3 候选及其指标明细，便于人工撰写答案",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"仓库路径不存在或不是目录: {repo}", file=sys.stderr)
        return 2

    key = build_answer_key(repo, args.data, args.mode, args.min_dir_files)

    if key["repo_head"] is None:
        print("警告: 该目录不是 Git 仓库，答案键不可复现（repo_head 为空）", file=sys.stderr)

    if args.show_t3_candidates:
        payload: object = key["T3"]
    else:
        payload = key

    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"已写出: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
