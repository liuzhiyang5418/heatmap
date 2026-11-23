"""按 `docs/evaluation-contract.md` §5 给试点答卷打分。

用法::

    python examples/evaluation/score_responses.py \
        --key answer_key_X.json --responses responses/ --out scores.json

评分规则（与契约 §3 的答案键口径一致）：

| 任务 | 满分 | 规则 |
|---|---|---|
| T1 | 3 | 与答案键的 top-3 求交集，每个正确文件 1 分 |
| T2 | 2 | 目录正确 1 分 + 比例正确（±1 个百分点）1 分 |
| T3 | 3 | **自动只做粗筛**：检出两项真实指标 2 分 + 说明「候选≠确诊」1 分；**必须人工复核** |
| T4 | 1 | 与 missing 集合完全一致 |

契约 §5 要求失败与超时单列，因此每个参与者都会输出 ``over_limit`` 与
``completed``（是否有任何一题留空），而不是把它们从统计里剔掉。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: T3 自动粗筛用的指标关键词；命中 ≥2 个才算"引用了两项真实指标"。
METRIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "commits": ("commit", "提交"),
    "churn": ("churn", "改动", "变更"),
    "contributors": ("contributor", "贡献者", "作者"),
    "gini": ("gini",),
    "age": ("age", "年龄", "天"),
    "loc": ("loc", "行数", "代码行"),
}

#: 「候选≠确诊」的表述关键词。
CAVEAT_KEYWORDS = ("候选", "不等于", "不代表", "不能确认", "需人工", "candidate", "not confirmed")


def _normalize_paths(raw: str) -> set[str]:
    """把参与者输入的路径串拆成集合，统一正斜杠、去空白。"""
    if not raw or raw.strip().upper() == "NONE":
        return set()
    parts = [part.strip().strip("`'\"") for part in raw.replace("\n", ",").split(",")]
    return {part.replace("\\", "/") for part in parts if part}


def score_t1(answer: str, key: dict[str, Any]) -> int:
    expected = {item["path"] for item in key["T1"]["answer"]}
    return len(_normalize_paths(answer) & expected)


def score_t2(answer: str, key: dict[str, Any]) -> tuple[int, str]:
    """目录 1 分 + 比例 1 分。作答形如 ``src 0.49`` / ``src 49%``。"""
    expected = key["T2"]["answer"]
    if not expected:
        return 0, "答案键里没有 T2 答案（目录都小于最小规模）"

    raw = (answer or "").strip().replace("\\", "/")
    parts = raw.split(None, 1)
    directory_part = parts[0].rstrip("/") if parts else ""
    ratio_part = parts[1] if len(parts) > 1 else ""

    points = 0
    notes: list[str] = []
    if directory_part == expected["directory"]:
        points += 1
    else:
        notes.append(f"目录应为 {expected['directory']}")

    # 比例允许 0.49 / 49% / 49 三种写法；容差 1 个百分点
    digits = "".join(ch for ch in ratio_part if ch.isdigit() or ch == ".")
    ratio_ok = False
    try:
        value = float(digits) if digits else -1.0
        for candidate in (value, value / 100.0):
            if abs(candidate - expected["ratio"]) <= 0.01:
                ratio_ok = True
    except ValueError:
        ratio_ok = False
    if ratio_ok:
        points += 1
    else:
        notes.append(f"比例应为 {expected['ratio']:.2%}")
    return points, "；".join(notes)


def score_t3(answer: str) -> tuple[int, str]:
    """粗筛：命中两项指标 2 分 + 有无 caveat 1 分。结果必须人工复核。"""
    text = (answer or "").lower()
    hits = [name for name, words in METRIC_KEYWORDS.items() if any(w in text for w in words)]
    points = min(len(hits), 2)
    if any(word in text for word in CAVEAT_KEYWORDS):
        points += 1
    detail = f"检出指标: {','.join(hits) or '无'}；caveat: {'有' if points > min(len(hits), 2) else '无'}"
    return points, detail


def score_t4(answer: str, key: dict[str, Any]) -> int:
    expected = set(key["T4"]["answer"])
    return 1 if _normalize_paths(answer) == expected else 0


def score_one(response: dict[str, Any], key: dict[str, Any]) -> dict[str, Any]:
    tasks = response.get("tasks", {})
    answers = {name: (entry.get("answer", "") if isinstance(entry, dict) else "") for name, entry in tasks.items()}
    elapsed = {
        name: (entry.get("elapsed_s", 0.0) if isinstance(entry, dict) else 0.0)
        for name, entry in tasks.items()
    }
    over_limit = [
        name for name, entry in tasks.items()
        if isinstance(entry, dict) and entry.get("over_limit")
    ]

    t2_points, t2_note = score_t2(answers.get("T2", ""), key)
    t3_points, t3_note = score_t3(answers.get("T3", ""))

    per_task = {
        "T1": score_t1(answers.get("T1", ""), key),
        "T2": t2_points,
        "T3": t3_points,
        "T4": score_t4(answers.get("T4", ""), key),
    }
    max_scores = {"T1": 3, "T2": 2, "T3": 3, "T4": 1}
    return {
        "participant": response.get("participant", "?"),
        "data": response.get("data", "?"),
        "scores": per_task,
        "total": sum(per_task.values()),
        "max_total": sum(max_scores.values()),
        "completion": sum(1 for value in answers.values() if value.strip()) / len(max_scores),
        "total_elapsed_s": round(sum(elapsed.values()), 2),
        "elapsed_by_task": elapsed,
        "over_limit": over_limit,
        "notes": {"T2": t2_note, "T3": f"{t3_note}（**需人工复核**）"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="给试点答卷打分")
    parser.add_argument("--key", required=True, help="答案键 JSON（build_answer_key.py 产出）")
    parser.add_argument("--responses", required=True, help="答卷 JSON 文件或目录")
    parser.add_argument("--out", help="汇总 JSON 输出路径；缺省打印到 stdout")
    args = parser.parse_args(argv)

    # utf-8-sig：兼容带 BOM 的 JSON（Windows 的编辑器/PowerShell 很容易写出 BOM）。
    key = json.loads(Path(args.key).read_text(encoding="utf-8-sig"))
    target = Path(args.responses)
    if not target.exists():
        print(f"答卷路径不存在: {target}", file=sys.stderr)
        return 2
    files = sorted(target.glob("*.json")) if target.is_dir() else [target]
    if not files:
        print(f"没有找到答卷: {target}", file=sys.stderr)
        return 2

    results = [
        score_one(json.loads(path.read_text(encoding="utf-8-sig")), key) for path in files
    ]

    print(f"{'参与者':<8}{'数据':<6}{'T1':>5}{'T2':>5}{'T3*':>5}{'T4':>5}{'总计':>7}{'耗时(s)':>9}  超时")
    print("-" * 62)
    for row in results:
        marks = row["scores"]
        print(
            f"{row['participant']:<8}{row['data']:<6}"
            f"{marks['T1']:>5}{marks['T2']:>5}{marks['T3']:>5}{marks['T4']:>5}"
            f"{row['total']:>4}/{row['max_total']:<3}{row['total_elapsed_s']:>8.1f}  "
            f"{','.join(row['over_limit']) or '-'}"
        )
    print("-" * 62)
    print("* T3 为自动粗筛结果，契约要求人工复核后再入表。")
    print("提醒：超时与未完成须单独报告，不能只统计成功者（契约 §5/§7）。")

    payload = {"key": str(args.key), "participants": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"\n已写出: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
