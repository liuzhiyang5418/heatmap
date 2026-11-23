"""试点引导脚本：按 `docs/evaluation-contract.md` 的 T1–T4 逐题记录答案与耗时。

用法（交互式，用于组内 2 人 pilot）::

    python examples/evaluation/run_pilot.py \
        --participant P01 --data X \
        --report heatmap_X.html \
        --out-dir responses

用法（非交互，仅用于演练脚本本身是否正常）::

    python examples/evaluation/run_pilot.py --participant TEST --data X \
        --answers sample_answers.json --out-dir /tmp/dryrun

设计约束（对齐契约 §9 数据最小化）：

- 只记录**匿名 participant id**、答案、耗时、是否超时；
- 不记录姓名、IP、设备、浏览器指纹；
- 不做"看到结果后再改目标"的操作——题目与时限在脚本里写死。

时限取自契约的「记录任务时限」要求，默认 180 秒/题；超时不会中断脚本，
而是在结果里标 ``over_limit: true``，交由评分脚本按契约 §5 单独报告。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TIME_LIMIT_S = 180.0

#: 任务定义与契约 §3 逐条对应。`prompt` 会被打印给参与者。
TASKS: dict[str, str] = {
    "T1": (
        "找出**分数最高的三个文件**（按报表中的分数列判断）。\n"
        "    作答格式: 三个路径，用英文逗号分隔\n"
        "    评分: 每个正确文件 1 分（0–3）"
    ),
    "T2": (
        "找出**高分文件比例最高的一级目录**（高分 = 分数落在前 25% 的文件）。\n"
        "    作答格式: 目录名 + 比例，空格分隔，如 `src 0.49` 或 `src 49%`\n"
        "    评分: 目录正确 1 分 + 比例正确 1 分（0–2）"
    ),
    "T3": (
        "解释**指定文件为什么需要检查**：请引用**两项真实指标**（如提交数、改动量、\n"
        "    贡献者数、Gini、年龄、LOC 中的任意两项），并说明「这是候选信号，不等于已确认债务」。\n"
        "    作答格式: 一句话说明（可多行，输入空行结束）\n"
        "    评分: 每项 1 分，共 0–3（需人工复核）"
    ),
    "T4": (
        "列出报表中**数据缺失（missing）的文件**。\n"
        "    作答格式: 路径列表，用英文逗号分隔；没有则输入 NONE\n"
        "    评分: 完全正确 1 分（0–1）"
    ),
}


def _read_multiline() -> str:
    """读取多行答案（空行结束），用于 T3。"""
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line.strip())
    return " ".join(lines)


def _ask(task: str, time_limit: float, reader: Callable[[], str]) -> dict[str, object]:
    """提问并计时；超时不打断，只标记。"""
    print(f"\n[{task}] {TASKS[task]}")
    print(f"    时限: {time_limit:.0f} 秒")
    started = time.perf_counter()
    answer = reader()
    elapsed = time.perf_counter() - started
    over_limit = elapsed > time_limit
    print(f"    用时 {elapsed:.1f}s" + ("  ** 超过时限 **" if over_limit else ""))
    return {"answer": answer, "elapsed_s": round(elapsed, 2), "over_limit": over_limit}


def run_interactive(participant: str, data: str, report: str, out_dir: Path, time_limit: float) -> int:
    print("=" * 66)
    print("githotmap 可用性试点")
    print("=" * 66)
    print(f"参与者: {participant}    数据集: {data}")
    print(f"报表:   {report}")
    print()
    print("说明：请在报表中查找答案；允许滚动、排序、悬停查看详情。")
    print("      计时从题目显示开始，到提交答案为止。")
    print("      任何一题都可以按 Ctrl+C 中止（会记为未完成，不丢已作答内容）。")
    input("      准备好后按回车开始 ...")

    responses: dict[str, dict[str, object]] = {}
    try:
        responses["T1"] = _ask("T1", time_limit, input)
        responses["T2"] = _ask("T2", time_limit, input)
        responses["T3"] = _ask("T3", time_limit, _read_multiline)
        responses["T4"] = _ask("T4", time_limit, input)
    except KeyboardInterrupt:
        print("\n\n已中止；以下已作答内容仍会保存。", file=sys.stderr)

    payload = {
        "participant": participant,
        "data": data,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "time_limit_s": time_limit,
        "tasks": responses,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{participant}_{data}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出: {target}")
    print("提醒：正式数据不要用组内成员；如使用，请在报告中披露便利样本与利益冲突。")
    return 0


def run_from_answers(
    participant: str, data: str, answers_path: Path, out_dir: Path, time_limit: float
) -> int:
    """非交互模式：从 JSON 读答案，用于演练脚本本身（不用于真实试点）。"""
    supplied = json.loads(answers_path.read_text(encoding="utf-8-sig"))
    responses: dict[str, dict[str, object]] = {}
    for task in TASKS:
        entry = supplied.get(task, {})
        answer = entry.get("answer", "") if isinstance(entry, dict) else str(entry)
        elapsed = float(entry.get("elapsed_s", 0.0)) if isinstance(entry, dict) else 0.0
        responses[task] = {
            "answer": answer,
            "elapsed_s": round(elapsed, 2),
            "over_limit": elapsed > time_limit,
        }

    payload = {
        "participant": participant,
        "data": data,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "time_limit_s": time_limit,
        "dry_run": True,
        "tasks": responses,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{participant}_{data}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出（演练）: {target}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="githotmap 可用性试点引导")
    parser.add_argument("--participant", required=True, help="匿名参与者 ID（如 P01）")
    parser.add_argument("--data", default="X", choices=["X", "Y"], help="数据集（X/Y）")
    parser.add_argument("--report", default="", help="要打开的 HTML 报表路径（仅提示用）")
    parser.add_argument("--out-dir", default="responses", help="答案输出目录")
    parser.add_argument(
        "--time-limit",
        type=float,
        default=DEFAULT_TIME_LIMIT_S,
        help=f"每题时限（秒，默认 {DEFAULT_TIME_LIMIT_S:.0f}）",
    )
    parser.add_argument(
        "--answers",
        help="非交互模式：从该 JSON 读答案（仅用于演练脚本，不用于真实试点）",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    if args.answers:
        return run_from_answers(
            args.participant, args.data, Path(args.answers), out_dir, args.time_limit
        )
    return run_interactive(args.participant, args.data, args.report, out_dir, args.time_limit)


if __name__ == "__main__":
    raise SystemExit(main())
