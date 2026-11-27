"""Build the speech-optimised 7-minute deck for githotmap.

Companion to ``demo-speech-script.md`` in this directory.

    pip install python-pptx
    python docs/process/presentations/build_slides.py

Output: demo-speech.pptx

Difference from ``githotmap-demo-7min.pptx``
--------------------------------------------
That deck is self-explanatory: each slide carries full sentences, so it reads
like a document. This deck is built the other way round — the *script* carries
the narration and each slide only keeps the keywords the speaker glances at.
Rules applied here:

* one claim per slide, expressed as a short line or a card title;
* no sentence longer than ~12 words anywhere on screen;
* numbers get their own slide and their own size (54 pt), not a table row;
* every slide maps 1:1 to a section of the script, in the same order.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

# ---------------------------------------------------------------- palette --
BG = RGBColor(0x0F, 0x14, 0x20)
PANEL = RGBColor(0x18, 0x1F, 0x30)
PANEL_2 = RGBColor(0x1E, 0x27, 0x40)
CODE_BG = RGBColor(0x0A, 0x0E, 0x18)
TEXT = RGBColor(0xE6, 0xE9, 0xF0)
MUTED = RGBColor(0x8B, 0x93, 0xA7)
ACCENT = RGBColor(0x4E, 0xA1, 0xFF)
WARN = RGBColor(0xFF, 0xD1, 0x66)
GOOD = RGBColor(0x4A, 0xDE, 0x80)
BAD = RGBColor(0xFF, 0x6B, 0x6B)

FONT = "Segoe UI"
MONO = "Consolas"

W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.85)
CONTENT_W = W - 2 * MARGIN

TITLE_TOP = Inches(0.96)
RULE_TOP = Inches(2.16)
BODY_TOP = Inches(2.45)
FOOTER_TOP = H - Inches(0.62)

DECK_TITLE = "githotmap"
FOOTER = "CS5351 Software Engineering  ·  6-person team"
TOTAL_SLIDES = 12


# ---------------------------------------------------------------- helpers --
def _rgb(shape, colour: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = colour


def _no_line(shape) -> None:
    shape.line.fill.background()


def new_slide(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BG
    return slide


def textbox(slide, left, top, width, height, *, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return box, tf


def write(tf, text, *, size, colour=TEXT, bold=False, align=PP_ALIGN.LEFT,
          space_after=6, first=False, font=FONT, line_spacing=1.15):
    para = tf.paragraphs[0] if first else tf.add_paragraph()
    para.alignment = align
    para.space_after = Pt(space_after)
    para.line_spacing = line_spacing
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = font
    run.font.color.rgb = colour
    return para


def header(slide, kicker: str, title: str, *, title_size=29):
    _, tf = textbox(slide, MARGIN, Inches(0.6), CONTENT_W, Inches(0.34))
    write(tf, kicker.upper(), size=12.5, colour=ACCENT, bold=True, space_after=0, first=True)
    _, tf2 = textbox(slide, MARGIN, TITLE_TOP, CONTENT_W, Inches(1.12))
    write(tf2, title, size=title_size, bold=True, space_after=0, first=True)
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, RULE_TOP, Inches(1.5), Pt(3))
    _rgb(rule, ACCENT)
    _no_line(rule)


def footer(slide, index: int):
    _, tf = textbox(slide, MARGIN, FOOTER_TOP, CONTENT_W, Inches(0.28))
    write(tf, FOOTER, size=10, colour=MUTED, space_after=0, first=True)
    _, tf2 = textbox(slide, W - MARGIN - Inches(1.2), FOOTER_TOP, Inches(1.2), Inches(0.28))
    write(tf2, f"{index} / {TOTAL_SLIDES}", size=10, colour=MUTED, align=PP_ALIGN.RIGHT,
          space_after=0, first=True)


def card(slide, left, top, width, height, *, fill=PANEL, line=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    _rgb(shape, fill)
    if line is None:
        _no_line(shape)
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(1.25)
    shape.adjustments[0] = 0.06
    shape.shadow.inherit = False
    return shape


def keyword_card(slide, left, top, width, height, title, keywords, *, accent=ACCENT,
                 title_size=19, kw_size=14):
    """Card whose body is 1–3 short keywords, never a sentence."""
    card(slide, left, top, width, height)
    _, tf = textbox(slide, left + Inches(0.3), top + Inches(0.26),
                    width - Inches(0.6), height - Inches(0.44))
    write(tf, title, size=title_size, bold=True, colour=accent, space_after=12, first=True)
    for line in keywords:
        write(tf, line, size=kw_size, colour=MUTED, space_after=7)


def code_block(slide, left, top, width, height, lines, *, size=13):
    card(slide, left, top, width, height, fill=CODE_BG)
    _, tf = textbox(slide, left + Inches(0.32), top + Inches(0.18),
                    width - Inches(0.64), height - Inches(0.36))
    first = True
    for line, colour in lines:
        write(tf, line, size=size, colour=colour, font=MONO, space_after=4, first=first)
        first = False


def big_stat(slide, left, top, width, value, label, *, colour=ACCENT):
    """A single number that carries the message of the slide."""
    _, tf = textbox(slide, left, top, width, Inches(0.9))
    write(tf, value, size=52, bold=True, colour=colour, align=PP_ALIGN.CENTER,
          space_after=0, first=True)
    _, tf2 = textbox(slide, left, top + Inches(0.92), width, Inches(0.6))
    write(tf2, label, size=13, colour=MUTED, align=PP_ALIGN.CENTER, space_after=0, first=True)


def band(slide, top, text, *, colour=ACCENT, size=15):
    """Full-width one-line takeaway under the content."""
    card(slide, MARGIN, top, CONTENT_W, Inches(0.62), fill=PANEL_2)
    _, tf = textbox(slide, MARGIN + Inches(0.3), top + Inches(0.17),
                    CONTENT_W - Inches(0.6), Inches(0.34))
    write(tf, text, size=size, colour=colour, bold=True, space_after=0, first=True)


# ------------------------------------------------------------------ slides --
def slide_title(prs):
    s = new_slide(prs)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, Inches(2.32), Inches(2.2), Pt(4))
    _rgb(bar, ACCENT)
    _no_line(bar)

    _, tf = textbox(s, MARGIN, Inches(2.56), Inches(11), Inches(0.34))
    write(tf, "CS5351 SOFTWARE ENGINEERING · GROUP PROJECT", size=12.5, colour=ACCENT,
          bold=True, space_after=0, first=True)

    _, tf = textbox(s, MARGIN, Inches(2.96), Inches(11.4), Inches(1.3))
    write(tf, DECK_TITLE, size=70, bold=True, space_after=0, first=True)

    _, tf = textbox(s, MARGIN, Inches(4.3), Inches(11.2), Inches(0.9))
    write(tf, "Turning Git history into an auditable technical-debt heatmap",
          size=23, colour=MUTED, space_after=0, first=True)

    _, tf = textbox(s, MARGIN, Inches(5.7), Inches(11.2), Inches(0.6))
    write(tf, "CLI  ·  4 modes + 3 composite  ·  308 tests  ·  93% coverage",
          size=14, colour=MUTED, space_after=0, first=True)
    return s


def slide_problem(prs):
    s = new_slide(prs)
    header(s, "The problem", "Which files are risky?")
    cw = (CONTENT_W - Inches(0.6)) / 3
    top = Inches(2.5)
    keyword_card(s, MARGIN, top, cw, Inches(2.0),
                 "Today", ["An opinion.", "Someone remembers a bad week."], accent=MUTED)
    keyword_card(s, MARGIN + cw + Inches(0.3), top, cw, Inches(2.0),
                 "Linters", ["See style, not behaviour.", "Who changed what, how often?"],
                 accent=MUTED)
    keyword_card(s, MARGIN + (cw + Inches(0.3)) * 2, top, cw, Inches(2.0),
                 "Ranked tools", ["A number.", "Rarely a confidence."], accent=MUTED)
    band(s, Inches(5.0), "A ranking you can act on — and check.", size=17)
    footer(s, 2)
    return s


def slide_what(prs):
    s = new_slide(prs)
    header(s, "What we built", "One command, one inspectable report")
    steps = ["Git history", "Metrics", "Scoring", "Report"]
    subs = ["commits · churn\ncontributors · age", "Gini · decay\nrecency",
            "4 modes + 3\ncomposite", "HTML + JSON\noffline"]
    box_w, gap = Inches(2.55), Inches(0.42)
    top = Inches(2.5)
    for i, (label, sub) in enumerate(zip(steps, subs)):
        left = MARGIN + (box_w + gap) * i
        card(s, left, top, box_w, Inches(1.5))
        _, tf = textbox(s, left + Inches(0.18), top + Inches(0.22), box_w - Inches(0.36),
                        Inches(0.34))
        write(tf, label, size=16, bold=True, colour=ACCENT, align=PP_ALIGN.CENTER,
              space_after=0, first=True)
        _, tf2 = textbox(s, left + Inches(0.18), top + Inches(0.7), box_w - Inches(0.36),
                         Inches(0.62))
        for j, line in enumerate(sub.split("\n")):
            write(tf2, line, size=11.5, colour=MUTED, align=PP_ALIGN.CENTER,
                  space_after=1, first=(j == 0))
        if i < len(steps) - 1:
            arrow = s.shapes.add_shape(
                MSO_SHAPE.RIGHT_ARROW, left + box_w + Inches(0.06), top + Inches(0.6),
                Inches(0.3), Inches(0.3))
            _rgb(arrow, MUTED)
            _no_line(arrow)

    _, tf = textbox(s, MARGIN, Inches(4.5), CONTENT_W, Inches(0.9))
    write(tf, "Cell size = lines of code.  Colour = risk.", size=17, colour=TEXT,
          space_after=6, first=True)
    write(tf, "Hover for the explanation. Sort to inspect.", size=17, colour=TEXT,
          space_after=0)
    band(s, Inches(5.95), "No server. No CDN. Opens offline.", colour=GOOD, size=15)
    footer(s, 3)
    return s


def slide_idea(prs):
    s = new_slide(prs)
    header(s, "Key idea", "Three choices that set us apart")
    cw = (CONTENT_W - Inches(0.6)) / 3
    top = BODY_TOP
    keyword_card(s, MARGIN, top, cw, Inches(2.35),
                 "1 · Behaviour, not style",
                 ["churn · ownership · age", "Changed under pressure,",
                  "not because it is long."])
    keyword_card(s, MARGIN + cw + Inches(0.3), top, cw, Inches(2.35),
                 "2 · Auditable",
                 ["Every skip has a reason code.", "Coverage is shown,",
                  "never implied."])
    keyword_card(s, MARGIN + (cw + Inches(0.3)) * 2, top, cw, Inches(2.35),
                 "3 · Reproducible",
                 ["Same repo → same digest.", "Two runs must agree,",
                  "on either OS."])
    band(s, Inches(5.25), "Both became our non-functional requirements.", colour=WARN)
    footer(s, 4)
    return s


def slide_related(prs):
    s = new_slide(prs)
    header(s, "Related work", "Borrow the scoring idea, add the audit trail")
    rows = [
        ["Source", "We took", "We added"],
        ["hotspot (Go)", "normalise-then-weight scoring", "audit trail; fixed its quotepath blind spot"],
        ["CodeCharta / CodeCity", "spatial overview of directories", "2D, self-contained, no build step"],
        ["SATD literature (P1–P6)", "TODO = evidence", "candidates, never proof"],
    ]
    shape = s.shapes.add_table(len(rows), 3, MARGIN, BODY_TOP, CONTENT_W, Inches(0.8) * 4)
    tbl = shape.table
    widths = [3.1, 4.0, 4.7]
    total = sum(widths)
    for idx, rel in enumerate(widths):
        tbl.columns[idx].width = Emu(int(CONTENT_W * rel / total))
    for r, row in enumerate(rows):
        tbl.rows[r].height = Inches(0.8)
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = PANEL_2 if r == 0 else PANEL
            cell.margin_left = Inches(0.16)
            cell.margin_right = Inches(0.1)
            cell.margin_top = Inches(0.06)
            cell.margin_bottom = Inches(0.06)
            tf = cell.text_frame
            tf.word_wrap = True
            para = tf.paragraphs[0]
            run = para.add_run()
            run.text = value
            run.font.size = Pt(13 if r == 0 else 14)
            run.font.name = FONT
            run.font.bold = r == 0
            run.font.color.rgb = ACCENT if r == 0 else TEXT
    band(s, Inches(6.05), "What we added: the audit trail.", colour=ACCENT, size=15)
    footer(s, 5)
    return s


def slide_arch(prs):
    s = new_slide(prs)
    header(s, "Architecture", "Modules are replaceable because of three contracts")
    layers = [
        ("Sources", "scanner (AST)   ·   todo (SATD)   ·   git (history)", ACCENT),
        ("Engine", "metrics → scoring → ranking", GOOD),
        ("Contracts", "path convention  ·  reason codes  ·  deterministic output", WARN),
        ("Hosts", "HTML renderer  ·  JSON renderer  ·  local Flask UI", MUTED),
    ]
    top = Inches(2.55)
    for i, (name, detail, colour) in enumerate(layers):
        y = top + Inches(0.8) * i
        card(s, MARGIN, y, Inches(2.2), Inches(0.64))
        _, tf = textbox(s, MARGIN + Inches(0.2), y + Inches(0.17), Inches(1.9), Inches(0.34))
        write(tf, name, size=14, bold=True, colour=colour, space_after=0, first=True)
        card(s, MARGIN + Inches(2.4), y, CONTENT_W - Inches(2.4), Inches(0.64), fill=PANEL_2)
        _, tf2 = textbox(s, MARGIN + Inches(2.65), y + Inches(0.18),
                         CONTENT_W - Inches(2.95), Inches(0.34))
        write(tf2, detail, size=12.5, colour=TEXT, space_after=0, first=True)

    band(s, Inches(5.95), "New renderer or parser plugs in — the core is untouched.",
         colour=GOOD, size=15)
    footer(s, 6)
    return s


def slide_challenge(prs):
    s = new_slide(prs)
    header(s, "The hard part", "Our worst bug produced no error at all")

    _, tf = textbox(s, MARGIN, BODY_TOP, CONTENT_W, Inches(0.5))
    write(tf, "Nothing crashed.   Nothing warned.", size=20, colour=BAD, bold=True,
          space_after=0, first=True)

    _, tf = textbox(s, MARGIN, Inches(3.1), CONTENT_W, Inches(0.9))
    write(tf, "Symptom:  a file with a Chinese name scored 0.0, with a mangled path.",
          size=15, colour=MUTED, space_after=4, first=True)
    write(tf, "Cause:  git escapes non-ASCII paths by default (core.quotepath).",
          size=15, colour=MUTED, space_after=0)

    code_block(s, MARGIN, Inches(4.25), CONTENT_W, Inches(1.5), [
        ('git side      "\\344\\270\\255\\346\\226\\207\\346\\250\\241\\345\\235\\227.py"', BAD),
        ("scanner side  中文模块.py", GOOD),
        ("intersection  none    →  commits = 2, loc = 0, score = 0.0", BAD),
    ], size=12.5)

    band(s, Inches(6.05),
         "A ranking that is silently wrong is worse than no ranking.", colour=WARN, size=16)
    footer(s, 7)
    return s


def slide_nfr2(prs):
    s = new_slide(prs)
    header(s, "NFR-2", "Robustness and auditability")
    cw = (CONTENT_W - Inches(0.6)) / 3
    top = BODY_TOP
    keyword_card(s, MARGIN, top, cw, Inches(2.15), "1 · One source",
                 ["scanner.Limitation is authoritative.", "The diagnostics enum",
                  "references it — no drift."])
    keyword_card(s, MARGIN + cw + Inches(0.3), top, cw, Inches(2.15), "2 · Guarded stages",
                 ["Every stage records a failure", "and its elapsed time.",
                  "Nothing is swallowed."])
    keyword_card(s, MARGIN + (cw + Inches(0.3)) * 2, top, cw, Inches(2.15), "3 · Strict mode",
                 ["--strict exits 3 on any", "degradation — even outside",
                  "the display limit."])
    band(s, Inches(5.05), "12 fault classes covered by tests.", colour=GOOD, size=16)
    footer(s, 8)
    return s


def slide_nfr3(prs):
    s = new_slide(prs)
    header(s, "NFR-3", "Reproducibility")
    cw = (CONTENT_W - Inches(0.3)) / 2
    top = BODY_TOP
    keyword_card(s, MARGIN, top, cw, Inches(1.55), "Injected clock",
                 ["One module owns every time source.", "Fix it, and ages stop drifting."])
    keyword_card(s, MARGIN + cw + Inches(0.3), top, cw, Inches(1.55), "Canonical output",
                 ["Clock and host fields dropped.", "Keys sorted, floats rounded, then hashed."])
    keyword_card(s, MARGIN, top + Inches(1.75), cw, Inches(1.55), "3 frozen snapshots",
                 ["Fixed commit dates, LF-locked.", "Same digest, either OS."])
    keyword_card(s, MARGIN + cw + Inches(0.3), top + Inches(1.75), cw, Inches(1.55),
                 "Enforced, not promised",
                 ["A test fails if any other module", "calls a time function."])
    band(s, Inches(6.15), "Enforced by a test, not a promise.", colour=GOOD, size=15)
    footer(s, 9)
    return s


def slide_evidence(prs):
    s = new_slide(prs)
    header(s, "Evidence · engineering", "What we can prove about the code itself")
    cw = (CONTENT_W - Inches(0.6)) / 4
    top = Inches(2.4)
    big_stat(s, MARGIN, top, cw, "308", "automated tests", colour=ACCENT)
    big_stat(s, MARGIN + cw + Inches(0.2), top, cw, "93%", "line coverage", colour=ACCENT)
    big_stat(s, MARGIN + (cw + Inches(0.2)) * 2, top, cw, "12", "fault classes", colour=ACCENT)
    big_stat(s, MARGIN + (cw + Inches(0.2)) * 3, top, cw, "0",
             "ruff + mypy findings", colour=GOOD)

    _, tf = textbox(s, MARGIN, Inches(4.3), CONTENT_W, Inches(0.9))
    write(tf, "Coverage gate set at 90%; measured 93%.", size=14, colour=MUTED,
          align=PP_ALIGN.CENTER, space_after=3, first=True)
    write(tf, "Static checks are whole-repository, version-pinned and enforced in CI "
              "on Ubuntu and Windows.", size=14, colour=MUTED, align=PP_ALIGN.CENTER,
          space_after=0)

    band(s, Inches(5.4), "Twelve fault classes, each asserting a reason code and the counts.",
         colour=GOOD, size=15)
    footer(s, 10)
    return s


def slide_evaluation(prs):
    s = new_slide(prs)
    header(s, "Evidence · evaluation", "Does the ranking track what actually churns?")
    cw = (CONTENT_W - Inches(0.4)) / 3
    top = Inches(2.4)
    big_stat(s, MARGIN, top, cw, "1.95×", "lift over chance", colour=GOOD)
    big_stat(s, MARGIN + cw + Inches(0.2), top, cw, "90%", "precision@10", colour=ACCENT)
    big_stat(s, MARGIN + (cw + Inches(0.2)) * 2, top, cw, "0.23",
             "rank correlation", colour=WARN)

    _, tf = textbox(s, MARGIN, Inches(4.2), CONTENT_W, Inches(0.5))
    write(tf, "90% against a 46% chance baseline  ·  recall@10 50%  ·  "
              "one iteration, 48 commits, 30 comparable files",
          size=13, colour=MUTED, align=PP_ALIGN.CENTER, space_after=0, first=True)

    card(s, MARGIN, Inches(5.0), CONTENT_W, Inches(1.05), fill=PANEL)
    _, tf = textbox(s, MARGIN + Inches(0.32), Inches(5.16), CONTENT_W - Inches(0.64),
                    Inches(0.8))
    write(tf, "The set is useful. The ordering inside it is not.", size=16, bold=True,
          colour=ACCENT, space_after=4, first=True)
    write(tf, "A shorter window returned 0.94× — reported as a failure, not dropped.",
          size=12.5, colour=MUTED, space_after=0)
    footer(s, 11)
    return s


def slide_takeaways(prs):
    s = new_slide(prs)
    header(s, "Takeaways", "A ranking you can act on — and check")
    cw = (CONTENT_W - Inches(0.6)) / 3
    top = BODY_TOP
    keyword_card(s, MARGIN, top, cw, Inches(1.75), "Answers",
                 ["Where should we look first?", "With evidence, not memory."])
    keyword_card(s, MARGIN + cw + Inches(0.3), top, cw, Inches(1.75), "Carried through",
                 ["Auditability and reproducibility", "shaped the architecture."])
    keyword_card(s, MARGIN + (cw + Inches(0.3)) * 2, top, cw, Inches(1.75), "Hardest lesson",
                 ["The dangerous bugs", "raise nothing at all."])
    band(s, Inches(4.55), "Next: the participant study (Q3) is still open.", colour=ACCENT,
         size=16)

    card(s, MARGIN, Inches(5.6), CONTENT_W, Inches(0.62))
    _, tf = textbox(s, MARGIN + Inches(0.28), Inches(5.73), CONTENT_W - Inches(0.56),
                    Inches(0.36))
    write(tf, "github.com/liuzhiyang5418/heatmap   ·   python -m githotmap analyze --mode roi",
          size=12.5, colour=ACCENT, font=MONO, space_after=0, first=True)
    footer(s, 12)
    return s


# -------------------------------------------------------------------- main --
def build(out_path: Path) -> Path:
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    prs.core_properties.title = "githotmap — 7-minute demo (speech version)"
    prs.core_properties.subject = "Companion to demo-speech-script.md"
    prs.core_properties.author = "CS5351 team"

    for builder in (
        slide_title, slide_problem, slide_what, slide_idea, slide_related,
        slide_arch, slide_challenge, slide_nfr2, slide_nfr3, slide_evidence,
        slide_evaluation, slide_takeaways,
    ):
        builder(prs)

    prs.save(out_path)
    return out_path


if __name__ == "__main__":
    target = Path(__file__).with_name("demo-speech.pptx")
    saved = build(target)
    print(f"wrote {saved} ({saved.stat().st_size} bytes, "
          f"{len(Presentation(saved).slides)} slides)")
