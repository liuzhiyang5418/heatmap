"""历史回放评估：用「后来真的被改了多少」检验「当初排得多前」。

这是 `docs/evaluation-contract.md` Q2（候选合理性）的**客观化**版本，不需要任何
参与者。做法是回溯验证：

    t0 时给仓库评分 → 排序 A
    t0..t1 之间每个文件的实际改动量 → 排序 B
    比较 A 与 B 的吻合程度

为什么不用外部参与者也能成立：这里的「答案」是既成的历史事实，不是人的判断，
所以不存在作者偏倚，且同一仓库任何人跑都得到同一结果。

边界（务必随结果一起报告，见 §"诚实的边界"）：
- 这是**回溯性验证**，不是因果证明。高重叠说明工具能识别后来确实高频改动的文件，
  不说明按它排期就一定正确；
- 只覆盖回放窗口内的改动，不代表长期趋势；
- 分数是启发式信号，契约 §1 的「候选 ≠ 确诊」原则同样适用。

用法::

    python examples/evaluation/historical_replay.py \
        --repo . --from <t0-sha> --to HEAD --mode roi --top-k 10 \
        --out replay.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from githotmap.core.pipeline import AnalysisPipeline


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _resolve_commit(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", f"{ref}^{{commit}}").strip()


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _window_stats(repo: Path, start: str, end: str) -> dict[str, Any]:
    """回放窗口的基本信息：提交数、天数。"""
    count = int(_git(repo, "rev-list", "--count", f"{start}..{end}").strip() or 0)
    # 取窗口首尾的提交时间计算跨度
    stamps = _git(repo, "log", "--format=%ct", f"{start}..{end}").split()
    days = 0.0
    if len(stamps) >= 2:
        values = sorted(int(value) for value in stamps)
        days = (values[-1] - values[0]) / 86400.0
    return {"commits": count, "days": round(days, 1)}


def _changed_files(repo: Path, start: str, end: str) -> dict[str, dict[str, int]]:
    """统计 start..end 之间每个文件的改动量与出现次数。

    ``--no-renames`` 是刻意的：重命名拆成删除 + 新增，口径简单可解释；
    ``-`` 表示二进制文件（numstat 不给行数），按 0 行计入但单独标记。
    """
    raw = _git(repo, "log", "--numstat", "--no-renames", "--format=", f"{start}..{end}")
    tally: dict[str, dict[str, int]] = defaultdict(lambda: {"churn": 0, "commits": 0, "binary": 0})
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        entry = tally[path.replace("\\", "/")]
        if added == "-" or deleted == "-":
            entry["binary"] += 1
        else:
            entry["churn"] += int(added) + int(deleted)
        entry["commits"] += 1
    return dict(tally)


def _deleted_files(repo: Path, start: str, end: str) -> list[str]:
    """窗口内被删除的文件（单独报告：删除可能是债务被偿还，不应算作预测错误）。"""
    raw = _git(repo, "diff", "--diff-filter=D", "--name-only", start, end)
    return sorted(line.strip().replace("\\", "/") for line in raw.splitlines() if line.strip())


def _ranks(values: list[float]) -> list[float]:
    """平均秩（处理并列），用于 Spearman。"""
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for index in range(position, end + 1):
            result[order[index]] = average
        position = end + 1
    return result


def _spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(rx)
    mean_x, mean_y = sum(rx) / n, sum(ry) / n
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry, strict=True))
    var_x = sum((a - mean_x) ** 2 for a in rx) ** 0.5
    var_y = sum((b - mean_y) ** 2 for b in ry) ** 0.5
    return covariance / (var_x * var_y) if var_x and var_y else 0.0


def _score_snapshot(repo: Path, commit: str, mode: str) -> dict[str, float]:
    """把仓库检出到提交状态再评分（用临时 worktree，不动原工作区）。"""
    temp_dir = Path(tempfile.mkdtemp(prefix="hotmap-replay-"))
    worktree = temp_dir / "snapshot"
    created = False
    try:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(worktree), commit],
            capture_output=True,
            check=True,
        )
        created = True
        result = AnalysisPipeline().run(worktree, mode=mode, limit=1_000_000)
        return {item.path: round(item.mode_score, 4) for item in result.files}
    finally:
        if created:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
                check=False,
            )
        shutil.rmtree(temp_dir, ignore_errors=True)


def evaluate(
    repo: Path, start: str, end: str, mode: str, top_k: int
) -> dict[str, Any]:
    scores = _score_snapshot(repo, start, mode)
    changed = _changed_files(repo, start, end)
    deleted = _deleted_files(repo, start, end)
    window = _window_stats(repo, start, end)

    # 只在「t0 被评分」的文件上比较——否则我们无法声称工具预测了它们
    comparable = {path: info for path, info in changed.items() if path in scores}
    if not comparable:
        raise SystemExit(
            "回放窗口内没有任何「t0 已评分且后来被改动」的文件；请换一个起点或更长的窗口"
        )

    tool_top = [path for path, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]]
    actual_top = [
        path
        for path, _ in sorted(comparable.items(), key=lambda kv: (-kv[1]["churn"], kv[0]))[:top_k]
    ]

    hits_in_changed = [path for path in tool_top if path in comparable]
    overlap = [path for path in tool_top if path in set(actual_top)]

    precision_at_k = len(hits_in_changed) / top_k
    recall_at_k = len(overlap) / top_k
    base_rate = len(comparable) / len(scores)
    lift = precision_at_k / base_rate if base_rate else 0.0

    # 样本量护栏：可比对文件太少时，任何比例都会被少数几个文件放大成噪声，
    # 此时指标只能当方向性提示，不能当结论。
    warnings: list[str] = []
    min_comparable = 2 * top_k
    if len(comparable) < min_comparable:
        warnings.append(
            f"可比对文件仅 {len(comparable)} 个（建议下限 {min_comparable} = 2×top_k）："
            "窗口过短或改动面过小，比例指标噪声大，不得作为结论"
        )
    if len(comparable) < top_k:
        warnings.append(
            f"可比对文件少于 top_k：Precision@{top_k} 的理论上限只有 "
            f"{len(comparable) / top_k:.1%}，偏低未必代表工具排序差"
        )

    # 秩相关：只看可比集合（工具排序 vs 实际改动量）
    ordered_by_tool = sorted(comparable.keys(), key=lambda p: scores[p])
    spearman = _spearman(
        [scores[path] for path in ordered_by_tool],
        [float(comparable[path]["churn"]) for path in ordered_by_tool],
    )

    return {
        "repo": str(repo),
        "from_commit": start,
        "to_commit": end,
        "mode": mode,
        "top_k": top_k,
        "window": window,
        "files_scored_at_t0": len(scores),
        "files_changed_in_window": len(changed),
        "files_comparable": len(comparable),
        "files_deleted_in_window": len(deleted),
        "deleted_files": deleted,
        "warnings": warnings,
        "metrics": {
            "precision_at_k": round(precision_at_k, 4),
            "recall_at_k": round(recall_at_k, 4),
            "random_baseline_at_k": round(base_rate, 4),
            "lift": round(lift, 2),
            "spearman_rho": round(spearman, 4),
        },
        "tool_top_k": [
            {
                "rank": index + 1,
                "path": path,
                "score": scores[path],
                "changed_in_window": path in comparable,
                "churn_in_window": comparable.get(path, {}).get("churn", 0),
            }
            for index, path in enumerate(tool_top)
        ],
        "actual_top_k": [
            {
                "rank": index + 1,
                "path": path,
                "churn_in_window": comparable[path]["churn"],
                "score_at_t0": scores[path],
            }
            for index, path in enumerate(actual_top)
        ],
        "caveats": [
            (
                "回溯性验证，不是因果证明：高重叠说明工具识别出了后来确实高频改动的文件，"
                "不说明按它排期一定正确"
            ),
            "只覆盖回放窗口内的改动，不代表长期趋势",
            (
                "历史热点信号的更新周期以周计：窗口短于一个迭代周期时，"
                "t0 的高分文件可能只是「这一周恰好没动」，会把 Lift 压到 1 以下"
            ),
            "分数是启发式信号；契约 §1 的「候选 ≠ 确诊」原则同样适用于此结果",
            "改动用 numstat 的 added+deleted 计，--no-renames 使重命名拆成删除+新增",
            "窗口内被删除的文件单独列出，不计入 comparable",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="历史回放评估（无需参与者）")
    parser.add_argument("--repo", default=".", help="仓库路径（默认当前目录）")
    parser.add_argument("--from", dest="start", required=True, help="回放起点提交（t0）")
    parser.add_argument("--to", dest="end", default="HEAD", help="回放终点（默认 HEAD）")
    parser.add_argument("--mode", default="roi", help="评分模式（默认 roi）")
    parser.add_argument("--top-k", type=int, default=10, help="比较的前 K 个文件（默认 10）")
    parser.add_argument("--out", help="结果 JSON 输出路径；缺省只打印摘要")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"仓库路径不存在或不是目录: {repo}", file=sys.stderr)
        return 2

    try:
        start = _resolve_commit(repo, args.start)
        end = _resolve_commit(repo, args.end)
    except subprocess.CalledProcessError as exc:
        print(f"无法解析提交: {exc}", file=sys.stderr)
        return 2

    if not _is_ancestor(repo, start, end):
        print(f"起点 {start[:8]} 不是终点 {end[:8]} 的祖先，无法回放", file=sys.stderr)
        return 2
    if start == end:
        print("起点与终点相同，窗口内没有改动", file=sys.stderr)
        return 2

    report = evaluate(repo, start, end, args.mode, args.top_k)

    metrics = report["metrics"]
    print("=" * 66)
    print("历史回放评估")
    print("=" * 66)
    print(f"起点: {start[:8]}    终点: {end[:8]}    模式: {args.mode}")
    print(
        f"窗口: {report['window']['commits']} 个提交 / {report['window']['days']} 天"
    )
    print(
        f"t0 评分文件: {report['files_scored_at_t0']}    "
        f"窗口内改动: {report['files_changed_in_window']}    "
        f"可比对: {report['files_comparable']}    "
        f"被删除: {report['files_deleted_in_window']}"
    )
    print("-" * 66)
    print(
        f"Top-{args.top_k} 命中: {round(metrics['precision_at_k'] * args.top_k)}/{args.top_k}  "
        f"(Precision@{args.top_k} = {metrics['precision_at_k']:.1%})"
    )
    print(
        f"随机基线:            "
        f"{metrics['random_baseline_at_k'] * args.top_k:.1f}/{args.top_k}  "
        f"({metrics['random_baseline_at_k']:.1%})"
    )
    print(f"Lift:                {metrics['lift']}x")
    print(f"Recall@{args.top_k}:            {metrics['recall_at_k']:.1%}")
    print(f"Spearman rho:        {metrics['spearman_rho']}")
    print("-" * 66)
    if report["warnings"]:
        print("!! 样本量不足，以下指标只能当方向性提示：")
        for warning in report["warnings"]:
            print(f"  · {warning}")
        print("-" * 66)
    print("诚实的边界：")
    for caveat in report["caveats"]:
        print(f"  · {caveat}")

    if args.out:
        payload = dict(report)
        payload["generated_at"] = datetime.now().astimezone().isoformat()
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已写出: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
