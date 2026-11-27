"""Render the 7-minute demo script as a printer-friendly PDF.

    python docs/process/presentations/build_script_pdf.py

Input : demo-speech-script.md
Output: demo-speech-script.html  (intermediate)
        demo-speech-script.pdf    (deliverable)

Why not a generic Markdown converter
------------------------------------
The script is a *speaking aid*, not a document. Two requirements drive the
layout, and neither is served by a generic md->pdf conversion:

1. **One script section per sheet of paper.** During the talk you flip paper,
   not scroll. So every "## Slide N" starts a new page, and a section is short
   enough to fit on one.
2. **The spoken text must dominate.** The verbatim lines (``> ...``) get the
   largest type and a tinted panel; the Chinese delivery notes get their own
   quieter style so your eye skips them while speaking.

A tiny purpose-built parser is also more robust here than pulling in a
Markdown library: the source uses a fixed subset, and this keeps the build
dependency-free.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "demo-speech-script.md"
HTML_OUT = HERE / "demo-speech-script.html"
PDF_OUT = HERE / "demo-speech-script.pdf"

EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


# ------------------------------------------------------------------ parsing --
def inline(text: str) -> str:
    """Escape, then apply the two inline constructs the script uses."""
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


_STOP = re.compile(r"^(#{1,4}\s|>|\||[-*]\s|---$)")


def md_to_html(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue

        if s == "---":
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if s.startswith(">"):
            block: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                block.append(lines[i].strip()[1:].strip())
                i += 1
            body = " ".join(x for x in block if x)
            out.append(f"<blockquote><p>{inline(body)}</p></blockquote>")
            continue

        if s.startswith("|"):
            rows: list[str] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            out.append(_table(rows))
            continue

        if re.match(r"^[-*]\s+", s):
            items: list[str] = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue

        # paragraph: swallow following plain lines
        para = [s]
        i += 1
        while i < n and lines[i].strip() and not _STOP.match(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        joined = " ".join(para)
        if joined.startswith("**Delivery**"):
            out.append(f'<p class="delivery">{inline(joined)}</p>')
        elif joined.startswith("**On screen**"):
            out.append(f'<p class="onscreen">{inline(joined)}</p>')
        else:
            out.append(f"<p>{inline(joined)}</p>")

    return "\n".join(out)


# --------------------------------------------------------------------- style --
CSS = """
@page { size: A4; margin: 15mm 15mm 13mm 15mm; }

* { box-sizing: border-box; }

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

body {
  font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 10.4pt; line-height: 1.55;
  color: #111827; margin: 0;
}

h1 {
  font-size: 23pt; line-height: 1.2; margin: 0 0 4px; letter-spacing: -0.2px;
}
h1 + p { color: #6b7280; font-size: 11pt; margin-top: 0; }

h2 {
  font-size: 15.5pt; line-height: 1.25; margin: 0 0 10px;
  padding-left: 11px; border-left: 5px solid #2563eb; color: #1e3a8a;
  page-break-before: always; page-break-after: avoid;
}
h2:first-of-type { page-break-before: auto; }

h3 {
  font-size: 10.5pt; text-transform: uppercase; letter-spacing: 0.6px;
  color: #6b7280; margin: 16px 0 6px; font-weight: 600;
  page-break-after: avoid;
}

p { margin: 7px 0; }

/* the spoken lines: the biggest, most readable block on the sheet */
blockquote {
  margin: 10px 0 12px; padding: 13px 17px;
  background: #eff6ff; border-left: 4px solid #2563eb; border-radius: 3px;
  font-size: 12.6pt; line-height: 1.72;
}
blockquote p { margin: 0; }

/* Chinese delivery note: deliberately quieter, you glance at it, not read it */
p.delivery {
  background: #fffbeb; border-left: 4px solid #d97706; border-radius: 3px;
  padding: 9px 13px; margin: 10px 0 4px; font-size: 10.4pt; line-height: 1.6;
  color: #78350f;
}
p.delivery strong { color: #b45309; }

p.onscreen {
  font-size: 10.2pt; color: #374151; background: #f3f4f6;
  border-radius: 3px; padding: 6px 11px; margin: 4px 0 8px;
}

table {
  width: 100%; border-collapse: collapse; margin: 10px 0 14px;
  font-size: 10.2pt; page-break-inside: avoid;
}
th, td { border: 1px solid #d1d5db; padding: 5px 9px; text-align: left; vertical-align: top; }
th { background: #e0ecff; color: #1e3a8a; font-weight: 600; }
tbody tr:nth-child(even) td { background: #f9fafb; }

ul { margin: 7px 0 12px; padding-left: 20px; }
li { margin: 4px 0; }

code {
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 0.92em;
  background: #eef2ff; color: #1e3a8a; padding: 1px 4px; border-radius: 3px;
}

hr { border: 0; border-top: 1px solid #e5e7eb; margin: 16px 0; }

blockquote, table, ul { page-break-inside: avoid; }
"""

PAGE_TEMPLATE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>githotmap — 7-minute demo script</title>
<style>{css}</style></head>
<body>
{body}
</body></html>
"""


def find_browser() -> str:
    for path in EDGE_CANDIDATES:
        if Path(path).exists():
            return path
    raise SystemExit("No Edge/Chrome found for PDF rendering.")


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")

    body = md_to_html(SRC.read_text(encoding="utf-8"))
    HTML_OUT.write_text(PAGE_TEMPLATE.format(css=CSS, body=body), encoding="utf-8")
    print(f"html  : {HTML_OUT.name} ({HTML_OUT.stat().st_size} bytes)")

    browser = find_browser()
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--no-sandbox",
        "--virtual-time-budget=8000",
        f"--print-to-pdf={PDF_OUT}",
        HTML_OUT.as_uri(),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not PDF_OUT.exists():
        print(proc.stdout[-800:])
        print(proc.stderr[-800:])
        raise SystemExit("PDF rendering failed")

    data = PDF_OUT.read_bytes()
    pages = re.search(rb"/Count\s+(\d+)", data)
    print(f"pdf   : {PDF_OUT.name} ({len(data)} bytes, "
          f"~{pages.group(1).decode() if pages else '?'} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
