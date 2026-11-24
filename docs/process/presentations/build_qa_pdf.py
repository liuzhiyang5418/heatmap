"""Render the Q&A prep sheet as a printer-friendly PDF.

    python docs/process/presentations/build_qa_pdf.py

Input : qa-preparation.md
Output: qa-preparation.pdf  (+ an .html intermediate)

Layout intent
-------------
The script PDF is read *while speaking*; this one is read *while being
questioned* — you have 5 seconds to find the right answer. So the layout
optimises for scanning, not for reading:

* one chapter per page, so "the evaluation question" is a page you can flip to;
* every question is a coloured, numbered block (Q1, Q23 …) so it can be
  referenced out loud — "that's Q23" — and found instantly;
* the star marks (★) keep their emphasis through colour, because they mark the
  questions most likely to be asked;
* the trap table gets red/green columns, since that page is a do/don't lookup;
* a plain <pre> block for the scored example, because mis-reading the arithmetic
  is the worst possible failure in a viva.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "答辩Q&A预案.md"
HTML_OUT = HERE / "qa-prep.html"
PDF_OUT = HERE / "答辩Q&A预案.pdf"

BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


# ------------------------------------------------------------------ parsing --
def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _table(rows: list[str]) -> str:
    head, body = _cells(rows[0]), [_cells(r) for r in rows[2:]]
    parts = ["<table><thead><tr>"]
    parts += [f"<th>{inline(c)}</th>" for c in head]
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>")
        parts += [f"<td>{inline(c)}</td>" for c in row]
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


_STOP = re.compile(r"^(#{1,4}\s|>|\||[-*]\s|\d+\.\s|```|---$)")


def md_to_html(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)

    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue

        # fenced code
        if s.startswith("```"):
            i += 1
            block: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
            continue

        if s == "---":
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            stars = re.match(r"^(★+)", title)
            if stars:
                mark = f'<span class="star">{stars.group(1)}</span>'
                title = title[len(stars.group(1)):]
                out.append(f"<h{level} class=\"qa\">{mark}{inline(title)}</h{level}>")
            elif level == 3:
                out.append(f'<h3 class="qa">{inline(title)}</h3>')
            else:
                out.append(f"<h{level}>{inline(title)}</h{level}>")
            i += 1
            continue

        if s.startswith(">"):
            block = []
            while i < n and lines[i].strip().startswith(">"):
                block.append(lines[i].strip()[1:].strip())
                i += 1
            body = " ".join(x for x in block if x)
            out.append(f"<blockquote><p>{inline(body)}</p></blockquote>")
            continue

        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            out.append(_table(rows))
            continue

        if re.match(r"^\d+\.\s+", s):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue

        if re.match(r"^[-*]\s+", s):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue

        para = [s]
        i += 1
        while i < n and lines[i].strip() and not _STOP.match(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out)


# --------------------------------------------------------------------- style --
CSS = """
@page { size: A4; margin: 14mm 14mm 12mm 14mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

body {
  font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 10.2pt; line-height: 1.55; color: #111827; margin: 0;
}

h1 { font-size: 22pt; line-height: 1.2; margin: 0 0 6px; }
h1::after {
  content: ""; display: block; width: 60px; height: 4px;
  background: #2563eb; margin-top: 10px;
}

h2 {
  font-size: 16pt; color: #1e3a8a; margin: 0 0 12px; padding-left: 12px;
  border-left: 5px solid #2563eb; page-break-before: always; page-break-after: avoid;
}
h2:first-of-type { page-break-before: auto; }

/* a question block: numbered, tinted, impossible to miss while flipping */
h3.qa {
  font-size: 11.4pt; line-height: 1.4; color: #fff; background: #2563eb;
  border-radius: 3px; padding: 6px 11px; margin: 15px 0 7px;
  page-break-after: avoid; page-break-inside: avoid;
}
h3.qa .star { color: #fde68a; margin-right: 3px; }

p { margin: 6px 0; }

/* the answer: the part you actually read out loud */
blockquote {
  margin: 0 0 8px; padding: 10px 14px;
  background: #f1f5fb; border-left: 3px solid #93b4f0; border-radius: 3px;
  font-size: 10.6pt; line-height: 1.62;
}
blockquote p { margin: 0 0 4px; }
blockquote p:last-child { margin-bottom: 0; }

pre {
  background: #0f172a; color: #e2e8f0; border-radius: 4px;
  padding: 10px 13px; margin: 8px 0 10px; overflow: hidden;
  page-break-inside: avoid;
}
pre code {
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 9.4pt;
  background: none; color: inherit; padding: 0; line-height: 1.5; white-space: pre-wrap;
}

table {
  width: 100%; border-collapse: collapse; margin: 9px 0 13px;
  font-size: 9.8pt; page-break-inside: avoid;
}
th, td { border: 1px solid #d6dbe4; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: #dbe7fb; color: #1e3a8a; font-weight: 600; }
tbody tr:nth-child(even) td { background: #f8fafc; }

/* the trap table: column 1 = the question, 2 = wrong, 3 = right */
table.trap td:nth-child(2) { background: #fef2f2; color: #991b1b; }
table.trap td:nth-child(3) { background: #f0fdf4; color: #14532d; }

ul, ol { margin: 6px 0 11px; padding-left: 20px; }
li { margin: 3px 0; }

code {
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 0.92em;
  background: #eef2ff; color: #1e3a8a; padding: 1px 4px; border-radius: 3px;
}

hr { border: 0; border-top: 1px solid #e5e7eb; margin: 14px 0; }

blockquote, table, pre, ul, ol { page-break-inside: avoid; }
"""

TEMPLATE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>答辩 Q&amp;A 预案</title>
<style>{css}</style></head>
<body>
{body}
</body></html>
"""


def find_browser() -> str:
    for path in BROWSERS:
        if Path(path).exists():
            return path
    raise SystemExit("No Edge/Chrome found.")


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")

    body = md_to_html(SRC.read_text(encoding="utf-8"))
    # mark the trap table so CSS can colour the wrong/right columns
    body = body.replace(
        "<table><thead><tr><th>问题</th>",
        '<table class="trap"><thead><tr><th>问题</th>',
    )
    HTML_OUT.write_text(TEMPLATE.format(css=CSS, body=body), encoding="utf-8")
    print(f"html  : {HTML_OUT.name} ({HTML_OUT.stat().st_size} bytes)")

    cmd = [
        find_browser(),
        "--headless=new", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer", "--virtual-time-budget=8000",
        f"--print-to-pdf={PDF_OUT}",
        HTML_OUT.as_uri(),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not PDF_OUT.exists():
        print(proc.stdout[-600:])
        print(proc.stderr[-600:])
        raise SystemExit("PDF rendering failed")

    data = PDF_OUT.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    print(f"pdf   : {PDF_OUT.name} ({len(data)} bytes, {pages} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
