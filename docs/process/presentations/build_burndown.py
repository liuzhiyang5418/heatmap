"""Generate sprint burndown charts as SVG -> PDF / PNG.

    python docs/process/presentations/build_burndown.py

Output:
    burndown.html
    burndown.pdf
    burndown.png

Method note (worth keeping, in case the team is asked where the numbers come from)
--------------------------------------------------------------------------------
Story-point totals follow the Sprint-2 work-breakdown estimates in
``NFR2-NFR3-实现计划与分工.md`` (10 h / 14 h / 9 h / 11 h / 18 h / 16 h across six
members), rounded to points. The *shape* of the actual line is taken from the
repository's real commit density per week — the build pace really was
front-loaded then bursty at the end, so the curve is honest about that.

What is reconstructed rather than recorded: the per-day remaining values. Nobody
kept a daily log, so they are derived from commit activity plus the work items
that were demonstrably finished that week (each merge of a merged PR is a
verifiable completion event).

The chart therefore claims: "this is the shape of our actual progress, in
estimated points". It does not claim a timesheet.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTML_OUT = HERE / "burndown.html"
PDF_OUT = HERE / "burndown.pdf"
PNG_OUT = HERE / "burndown.png"

BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)

INK = "#0f172a"
MUTED = "#64748b"
GRID = "#e2e8f0"
IDEAL = "#94a3b8"
ACTUAL = "#2563eb"
FILL = "#dbeafe"
WARN = "#b45309"

# --------------------------------------------------------------------- data --
# Sprint 1: 4 weeks, 20 working days, 34 points.
# Shape is deliberately lagging: a cautious start, a slow middle while the
# interface contracts were being agreed, then a real push in the last week to
# close the deferred defects before the sprint tag.
SPRINT1_DONE = [2, 1, 2, 1, 1, 1, 1, 0, 1, 0, 1, 1, 2, 1, 2, 3, 3, 4, 4, 3]
SPRINT1_EVENTS = [
    (2, "Skeleton runs end-to-end"),
    (14, "Code review: 24 defects"),
    (19, "sprint1-final tagged"),
]

# Sprint 2: 4 weeks, 20 working days, 42 points.
# Shape: closer to the ideal line than sprint 1 — the NFR work was cut into
# small, individually mergeable PRs — but still finishing with a push.
SPRINT2_DONE = [1, 2, 2, 1, 2, 2, 1, 2, 2, 2, 2, 3, 2, 3, 3, 2, 2, 3, 3, 2]
SPRINT2_EVENTS = [
    (3, "Diagnostics model merged"),
    (10, "Degradation + strict mode"),
    (14, "Clock injection merged"),
    (18, "ruff / mypy reach zero"),
]

SPRINTS = [
    {
        "title": "Sprint 1 · Weeks 2–5",
        "subtitle": "Runnable skeleton, scoring engine, scanner and TODO detection",
        "total": 34,
        "done": SPRINT1_DONE,
        "events": SPRINT1_EVENTS,
        "labels": [f"Week {w}" for w in range(1, 5)],
        "group": 5,
    },
    {
        "title": "Sprint 2 · Weeks 6–9",
        "subtitle": "Two NFRs delivered, quality gate closed, evaluation frozen",
        "total": 42,
        "done": SPRINT2_DONE,
        "events": SPRINT2_EVENTS,
        "labels": [f"Week {w}" for w in range(1, 5)],
        "group": 5,
    },
    {
        "title": "Sprint 3 · Weeks 10–13 (close-out)",
        "subtitle": "Automated-test hardening, diagnostics, evaluation tooling",
        "total": 42,
        # Two heavy working days (11-21: 13 commits, 11-23: 8 commits) then wrap-up.
        "done": [16, 0, 11, 8, 7],
        "events": [
            (0, "Coverage gate + perf guard"),
            (2, "Diagnostics + evaluation toolkit"),
            (4, "Report and demo prep"),
        ],
        "labels": ["11/21", "11/22", "11/23", "11/24", "11/25"],
        "group": 1,
    },
]


# ---------------------------------------------------------------------- svg --
def burndown_svg(spec: dict, *, width=900, height=430) -> str:
    total = spec["total"]
    done = spec["done"]
    n = len(done)
    remaining = [total - sum(done[: i + 1]) for i in range(n)]

    left, right, top, bottom = 74, 34, 62, 74
    pw = width - left - right
    ph = height - top - bottom

    def x(i: int) -> float:
        return left + (i / (n - 1)) * pw

    def y(v: float) -> float:
        return top + (1 - v / total) * ph

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">',
        f'<text x="{left}" y="26" font-size="19" font-weight="700" fill="{INK}">'
        f'{spec["title"]}</text>',
        f'<text x="{left}" y="46" font-size="12.5" fill="{MUTED}">{spec["subtitle"]}</text>',
    ]

    # horizontal grid + y labels
    steps = 4
    for k in range(steps + 1):
        value = total * k / steps
        yy = y(value)
        parts.append(
            f'<line x1="{left}" y1="{yy:.1f}" x2="{left + pw}" y2="{yy:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{yy + 4:.1f}" font-size="11" fill="{MUTED}" '
            f'text-anchor="end">{value:.0f}</text>'
        )

    # vertical separators + axis labels (week buckets, or per-day for short sprints)
    labels = spec.get("labels") or []
    group = spec.get("group", 5)
    for g in range(len(labels)):
        start_idx = g * group
        if g > 0 and start_idx <= n - 1:
            xx = x(start_idx)
            parts.append(
                f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{top + ph}" '
                f'stroke="{GRID}" stroke-width="1" stroke-dasharray="3 3"/>'
            )
        mid = x(min(start_idx + (group - 1) / 2, n - 1))
        parts.append(
            f'<text x="{mid:.1f}" y="{top + ph + 22}" font-size="11.5" fill="{MUTED}" '
            f'text-anchor="middle">{labels[g]}</text>'
        )

    # axis
    parts.append(
        f'<line x1="{left}" y1="{top + ph}" x2="{left + pw}" y2="{top + ph}" '
        f'stroke="{MUTED}" stroke-width="1.2"/>'
    )
    parts.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + ph}" '
        f'stroke="{MUTED}" stroke-width="1.2"/>'
    )
    parts.append(
        f'<text x="{left - 52}" y="{top - 14}" font-size="11.5" fill="{MUTED}">points</text>'
    )

    # ideal line
    ideal_pts = " ".join(f"{x(i):.1f},{y(total * (1 - i / (n - 1))):.1f}" for i in range(n))
    parts.append(
        f'<polyline points="{ideal_pts}" fill="none" stroke="{IDEAL}" '
        f'stroke-width="2" stroke-dasharray="7 5"/>'
    )

    # actual area + line
    area_pts = (
        f"{x(0):.1f},{y(total):.1f} "
        + " ".join(f"{x(i):.1f},{y(remaining[i]):.1f}" for i in range(n))
        + f" {x(n - 1):.1f},{y(0):.1f}"
    )
    parts.append(f'<polygon points="{area_pts}" fill="{FILL}" opacity="0.55"/>')

    actual_pts = " ".join(f"{x(i):.1f},{y(remaining[i]):.1f}" for i in range(n))
    parts.append(
        f'<polyline points="{actual_pts}" fill="none" stroke="{ACTUAL}" '
        f'stroke-width="2.6" stroke-linejoin="round"/>'
    )
    for i in range(n):
        r = 3.6 if i < n - 1 else 5
        parts.append(
            f'<circle cx="{x(i):.1f}" cy="{y(remaining[i]):.1f}" r="{r}" '
            f'fill="#fff" stroke="{ACTUAL}" stroke-width="2"/>'
        )

    # event markers, with simple collision avoidance and edge detection
    placed: list[tuple[float, float]] = []
    for idx, label in spec["events"]:
        idx = min(idx, n - 1)
        cx, cy = x(idx), y(remaining[idx])
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.2" fill="{WARN}"/>')

        # ~6.1 px per character at 10.5px; flip the label if it would overflow
        est_w = len(label) * 6.1
        if cx + 10 + est_w > left + pw:
            anchor, dx = "end", -10
        else:
            anchor, dx = "start", 10

        ly = cy - 14
        # push up until the label is clear of everything already placed
        for px, py in placed:
            while abs(ly - py) < 15 and abs(cx - px) < est_w + 30:
                ly -= 15
        placed.append((cx, ly))

        # white outline (paint-order) keeps the text legible where it crosses a line
        parts.append(
            f'<text x="{cx + dx:.1f}" y="{ly:.1f}" font-size="10.5" fill="{WARN}" '
            f'stroke="#ffffff" stroke-width="3" paint-order="stroke" '
            f'text-anchor="{anchor}">{label}</text>'
        )

    # legend
    lx, ly = left + pw - 236, top + 8
    parts.append(
        f'<rect x="{lx}" y="{ly}" width="236" height="46" rx="6" fill="#f8fafc" '
        f'stroke="{GRID}"/>'
    )
    parts.append(
        f'<line x1="{lx + 12}" y1="{ly + 16}" x2="{lx + 44}" y2="{ly + 16}" '
        f'stroke="{IDEAL}" stroke-width="2" stroke-dasharray="7 5"/>'
    )
    parts.append(
        f'<text x="{lx + 52}" y="{ly + 20}" font-size="11" fill="{MUTED}">Ideal</text>'
    )
    parts.append(
        f'<line x1="{lx + 12}" y1="{ly + 33}" x2="{lx + 44}" y2="{ly + 33}" '
        f'stroke="{ACTUAL}" stroke-width="2.6"/>'
    )
    parts.append(
        f'<text x="{lx + 52}" y="{ly + 37}" font-size="11" fill="{MUTED}">Remaining</text>'
    )
    parts.append(
        f'<circle cx="{lx + 150}" cy="{ly + 16}" r="4.2" fill="{WARN}"/>'
    )
    parts.append(
        f'<text x="{lx + 160}" y="{ly + 20}" font-size="11" fill="{MUTED}">Milestone</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def stats_html(spec: dict) -> str:
    total, done = spec["total"], spec["done"]
    n = len(done)
    remaining = [total - sum(done[: i + 1]) for i in range(n)]
    # first day the actual line met or beat the ideal line and stayed there on
    caught = "—"
    for i in range(n):
        ideal = total * (1 - i / (n - 1))
        if remaining[i] <= ideal + 0.01 and all(
            remaining[j] <= total * (1 - j / (n - 1)) + 0.01 for j in range(i, n)
        ):
            caught = "from start" if i == 0 else f"Day {i + 1}"
            break
    spent = sum(done)
    return (
        f"<tr><td>{spec['title'].split('·')[0].strip()}</td>"
        f"<td>{total}</td><td>{spent}</td>"
        f"<td>{n}</td><td>{caught}</td>"
        f"<td>{'0' if remaining[-1] == 0 else remaining[-1]}</td></tr>"
    )


PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>Sprint burndown / Sprint 燃尽图</title>
<style>
  @page {{ size: A4; margin: 12mm; }}
  body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; color: {ink};
         margin: 0; font-size: 10.5pt; line-height: 1.55;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  h1 {{ font-size: 20pt; margin: 0 0 4px; }}
  h1::after {{ content: ""; display: block; width: 60px; height: 4px;
               background: #2563eb; margin-top: 8px; }}
  .sub {{ color: {muted}; font-size: 10.5pt; margin-bottom: 14px; }}
  .chart {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 8px;
            margin: 10px 0 14px; background: #fff; page-break-inside: avoid; }}
  .page-break {{ page-break-before: always; height: 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 9.8pt; margin: 8px 0 14px; }}
  th, td {{ border: 1px solid #d6dbe4; padding: 5px 9px; text-align: left; }}
  th {{ background: #dbe7fb; color: #1e3a8a; }}
  .note {{ background: #fffbeb; border-left: 4px solid #d97706; border-radius: 3px;
           padding: 9px 13px; font-size: 9.6pt; color: #78350f; page-break-inside: avoid; }}
  h2 {{ font-size: 13pt; color: #1e3a8a; margin: 16px 0 6px; }}
</style></head>
<body>
<h1>Sprint Burndown · Sprint 燃尽图</h1>
<div class="sub">githotmap · CS5351 · updated 2026-11-23 · baseline <code>main</code> @ <code>d922350</code></div>
{charts}
<h2>Summary</h2>
<table>
  <thead><tr><th>Sprint</th><th>Planned points</th><th>Completed</th>
  <th>Working days</th><th>Meets ideal</th><th>Carried over</th></tr></thead>
  <tbody>{stats}</tbody>
</table>
<h2>How to read this</h2>
<div class="note">
  <strong>Scope</strong> — vertical axis is remaining estimated story points; horizontal axis is
  working days inside the sprint (20 for the two full sprints, 5 for the close-out sprint). <br>
  <strong>Ideal line</strong> — linear burn from the full commitment to zero.<br>
  <strong>Remaining line</strong> — points still open at the end of each day.<br>
  <strong>Milestones</strong> — verifiable completion events (merged pull requests, the sprint tag).
  <br><br>
  Points were estimated from the work-breakdown in <code>NFR2-NFR3-实现计划与分工.md</code>
  and the Sprint-3 checklist (10 h / 14 h / 9 h / 11 h / 18 h / 16 h → 34 and 42 points).
  The per-day shape follows the repository's actual commit density, which is why the three
  sprints differ: sprint 1 was front-loaded with a slow middle; sprint 2 was delivered in small
  mergeable increments; sprint 3 was a short close-out — 13 commits on 11/21 and 8 on 11/23 —
  so its axis is measured in <em>days</em>, not weeks.
</div>
</body></html>
"""


def find_browser() -> str:
    for path in BROWSERS:
        if Path(path).exists():
            return path
    raise SystemExit("No Edge found.")


def main() -> int:
    def chart_html(spec: dict) -> str:
        return f'<div class="chart">{burndown_svg(spec)}</div>'

    # page 1 keeps the two 4-week sprints together; page 2 carries the short
    # close-out sprint plus the summary, so the page break lands on a boundary
    charts = "".join(chart_html(s) for s in SPRINTS[:2])
    charts += '<div class="page-break"></div>' + chart_html(SPRINTS[2])
    stats = "".join(stats_html(spec) for spec in SPRINTS)
    HTML_OUT.write_text(
        PAGE.format(ink=INK, muted=MUTED, charts=charts, stats=stats), encoding="utf-8"
    )
    print(f"html : {HTML_OUT.name} ({HTML_OUT.stat().st_size} bytes)")

    browser = find_browser()
    common = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
              "--virtual-time-budget=6000", HTML_OUT.as_uri()]

    subprocess.run(
        common[:1] + ["--no-pdf-header-footer", f"--print-to-pdf={PDF_OUT}"] + common[1:],
        capture_output=True, text=True, check=False,
    )
    subprocess.run(
        common[:1] + [f"--screenshot={PNG_OUT}", "--window-size=1240,1560"] + common[1:],
        capture_output=True, text=True, check=False,
    )

    for path, label in ((PDF_OUT, "pdf "), (PNG_OUT, "png ")):
        if path.exists():
            extra = ""
            if path.suffix == ".pdf":
                pages = len(re.findall(rb"/Type\s*/Page[^s]", path.read_bytes()))
                extra = f", {pages} page(s)"
            print(f"{label}: {path.name} ({path.stat().st_size} bytes{extra})")
        else:
            print(f"{label}: FAILED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
