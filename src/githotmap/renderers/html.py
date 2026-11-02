"""Render a self-contained interactive HTML heatmap.

Cell area approximates LOC, color represents the score, hovering displays
details, and table headers control sorting. No external CDN is required.
"""

from __future__ import annotations

import json
from typing import Any

from githotmap.core.models import AnalysisResult
from githotmap.renderers.base import Renderer
from githotmap.renderers.registry import register

# The placeholder is replaced by serialized JSON in render().
_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Git Technical Debt Heatmap</title>
<style>
  :root { --bg:#0f1420; --panel:#181f30; --text:#e6e9f0; --muted:#8b93a7; --accent:#4ea1ff; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.5 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
  header { padding:22px 28px 12px; border-bottom:1px solid #232b40; }
  h1 { margin:0 0 4px; font-size:22px; }
  .meta { color:var(--muted); font-size:13px; }
  .legend { display:flex; align-items:center; gap:10px; margin-top:12px; font-size:12px; color:var(--muted); }
  .legend .bar { width:180px; height:10px; border-radius:5px;
                 background:linear-gradient(90deg, hsl(120,70%,45%), hsl(60,70%,45%), hsl(0,70%,45%)); }
  .legend { flex-wrap:wrap; }
  .note { color:var(--muted); font-size:12px; }
  main { padding:20px 28px 40px; }
  #heatmap { display:flex; flex-wrap:wrap; gap:3px; min-height:160px; }
  .cell { flex-basis:70px; flex-grow:1; height:26px; border-radius:3px; cursor:pointer;
          transition:transform .06s, box-shadow .06s; }
  .cell:hover { transform:scale(1.06); box-shadow:0 0 0 2px #fff; z-index:2; }
  .panel { background:var(--panel); border:1px solid #232b40; border-radius:10px;
           padding:16px 18px; margin-top:22px; }
  .panel h2 { margin:0 0 12px; font-size:17px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:7px 10px; border-bottom:1px solid #232b40; white-space:nowrap; }
  th { color:var(--accent); cursor:pointer; user-select:none; position:sticky; top:0; background:var(--panel); }
  th:hover { text-decoration:underline; }
  tr:hover td { background:#1e2740; }
  td.path { white-space:normal; word-break:break-all; }
  #tooltip { position:fixed; display:none; max-width:380px; background:#0a0e18; color:var(--text);
             border:1px solid #334; border-radius:8px; padding:10px 12px; font-size:12px;
             pointer-events:none; z-index:50; box-shadow:0 6px 24px rgba(0,0,0,.5); }
  #tooltip .p { color:var(--accent); font-weight:600; margin-bottom:4px; word-break:break-all; }
  #tooltip .s { color:#ffd166; font-weight:700; }
  #tooltip ul { margin:6px 0 0; padding-left:16px; }
</style>
</head>
<body>
<header>
  <h1>Git Technical Debt Heatmap</h1>
  <div class="meta" id="meta"></div>
  <div class="legend">
    <span>Low score</span><div class="bar"></div><span>High score</span><span>Gray: empty file or missing data</span>
    <span style="margin-left:16px">Cell area ≈ lines of code (LOC)</span>
  </div>
  <p class="note">Scores are candidate signals for human review. The current model marks both empty files and missing file data as missing. Status does not establish scan completeness; sample confidence is a commit-count heuristic, not a probability.</p>
</header>
<main>
  <div class="panel"><div id="heatmap"></div></div>
  <div class="panel">
    <h2>File details (click a heading to sort)</h2>
    <table id="table">
      <thead><tr>
        <th data-key="path">Path</th>
        <th data-key="mode_score">Score</th>
        <th data-key="commits">Commits</th>
        <th data-key="churn">Churn</th>
        <th data-key="unique_contributors">Contributors</th>
        <th data-key="gini">Gini</th>
        <th data-key="age_days">Age (days)</th>
        <th data-key="lines_of_code">LOC</th>
        <th>Data status</th>
        <th data-key="confidence">Sample confidence</th>
        <th>Score explanations</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</main>
<div id="tooltip"></div>
<script>
const DATA = __DATA__;

function scoreColor(score) {
  const s = Math.max(0, Math.min(100, Number(score) || 0));
  const hue = 120 * (1 - s / 100); // 120=green → 0=red
  return `hsl(${hue}, 70%, 45%)`;
}

function fmt(n) {
  if (n === null || n === undefined) return '-';
  const v = Number(n);
  if (!isFinite(v)) return '-';
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1);
}

function reasonsOf(f) {
  const r = f.reasoning || {};
  const list = r[DATA.mode] || Object.values(r).find(a => a && a.length) || [];
  return list;
}

function statusText(f) {
  if (f.status === 'missing') return 'Empty file or missing data';
  if (f.status === 'low_confidence') return 'Limited sample';
  return f.status === 'ok' || !f.status ? 'No issue flagged' : String(f.status);
}

function textElement(tag, text, className = '') {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

function renderMeta() {
  const n = (DATA.files || []).length;
  const el = document.getElementById('meta');
  el.textContent = `Repository: ${DATA.repo_path} · Mode: ${DATA.mode} · Files: ${n} · Analyzed: ${DATA.analyzed_at}`;
}

function showTooltip(anchor, f) {
  const tip = document.getElementById('tooltip');
  tip.replaceChildren();
  tip.appendChild(textElement('div', f.path, 'p'));
  tip.appendChild(textElement('div', f.status === 'missing' ? 'Score unavailable' : `${fmt(f.mode_score)} / 100`, 's'));
  tip.appendChild(textElement('div', `Status: ${statusText(f)} · Sample confidence: ${fmt(f.confidence)}`));
  tip.appendChild(textElement('div',
    `Commits ${fmt(f.metrics.commits)} · Churn ${fmt(f.metrics.churn)} · ` +
    `Contributors ${fmt(f.metrics.unique_contributors)} · LOC ${fmt(f.metrics.lines_of_code)}`));
  const reasons = reasonsOf(f);
  if (reasons.length) {
    const list = document.createElement('ul');
    reasons.forEach(reason => list.appendChild(textElement('li', reason)));
    tip.appendChild(list);
  }
  tip.style.display = 'block';
  moveTooltip();
  function moveTooltip() {
    const r = anchor.getBoundingClientRect();
    const x = Math.min(r.right + 8, window.innerWidth - tip.offsetWidth - 12);
    const y = Math.min(r.top, window.innerHeight - tip.offsetHeight - 12);
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  tip._move = moveTooltip;
}

function hideTooltip() {
  const tip = document.getElementById('tooltip');
  tip.style.display = 'none';
  tip._move = null;
}

document.addEventListener('mousemove', e => {
  const tip = document.getElementById('tooltip');
  if (tip._move) tip._move();
});

function renderHeatmap(files) {
  const container = document.getElementById('heatmap');
  container.innerHTML = '';
  files.forEach(f => {
    const cell = document.createElement('div');
    cell.className = 'cell';
    const loc = Number(f.metrics.lines_of_code) || 1;
    cell.style.flexGrow = Math.max(loc, 1);
    cell.style.background = f.status === 'missing' ? '#777f8b' : scoreColor(f.mode_score);
    cell.dataset.path = f.path;
    cell.addEventListener('mouseenter', () => showTooltip(cell, f));
    cell.addEventListener('mouseleave', hideTooltip);
    cell.addEventListener('click', () => highlightRow(f.path));
    container.appendChild(cell);
  });
}

function highlightRow(path) {
  const rows = document.querySelectorAll('#tbody tr');
  let selected = null;
  rows.forEach(row => {
    const match = row.dataset.path === path;
    row.style.background = match ? '#24304d' : '';
    if (match) selected = row;
  });
  if (selected) selected.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

let sortKey = 'mode_score';
let sortDesc = true;

function renderTable(files) {
  const tbody = document.getElementById('tbody');
  const ordered = [...files].sort((a, b) => {
    const va = a[sortKey] !== undefined ? a[sortKey] : a.metrics[sortKey];
    const vb = b[sortKey] !== undefined ? b[sortKey] : b.metrics[sortKey];
    if (sortKey === 'path') {
      const order = String(va).localeCompare(String(vb));
      return sortDesc ? -order : order;
    }
    const na = Number(va) || 0, nb = Number(vb) || 0;
    return sortDesc ? nb - na : na - nb;
  });
  tbody.innerHTML = '';
  ordered.forEach(f => {
    const tr = document.createElement('tr');
    tr.dataset.path = f.path;
    const values = [f.path, f.status === 'missing' ? '-' : fmt(f.mode_score), fmt(f.metrics.commits), fmt(f.metrics.churn),
      fmt(f.metrics.unique_contributors), fmt(f.metrics.gini), fmt(f.metrics.age_days),
      fmt(f.metrics.lines_of_code), statusText(f), fmt(f.confidence), reasonsOf(f).join('; ')];
    values.forEach((value, index) => tr.appendChild(textElement('td', value, index === 0 ? 'path' : '')));
    tr.addEventListener('mouseenter', () => {
      const cell = [...document.querySelectorAll('.cell')].find(item => item.dataset.path === f.path);
      if (cell) showTooltip(cell, f);
    });
    tr.addEventListener('mouseleave', hideTooltip);
    tbody.appendChild(tr);
  });
}

function wireSort() {
  document.querySelectorAll('#table th').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (!key) return;
      if (sortKey === key) sortDesc = !sortDesc; else { sortKey = key; sortDesc = key !== 'path'; }
      renderTable(DATA.files || []);
    });
  });
}

renderMeta();
renderHeatmap(DATA.files || []);
renderTable(DATA.files || []);
wireSort();
</script>
</body>
</html>
"""


@register("html")
class HTMLRenderer(Renderer):
    """Render an analysis result as a self-contained interactive heatmap."""

    name = "html"

    def render(self, result: AnalysisResult, **kwargs: Any) -> str:
        data_json = json.dumps(result.to_dict(), ensure_ascii=False).replace("</", "<\\/")
        return _HTML_TEMPLATE.replace("__DATA__", data_json)
