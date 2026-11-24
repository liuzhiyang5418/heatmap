# githotmap: Turning Git History into an Auditable Maintenance Worklist

**Final Report — CS5351 Software Engineering Group Project**

Team: six members (M1–M6). Repository: `liuzhiyang5418/heatmap`. Version 0.1.0.

> **Draft status.** This is an English draft for the team to polish. Personal names and
> individual bios are deliberately left as `[Name]` placeholders — they were not in the
> repository and must not be invented. Every quantitative claim below is traceable to a
> file, a commit, or a CI run named in the text.

---

## Abstract

Teams routinely know that maintenance effort must be prioritised, yet rarely have an
auditable way to say *which file first*. Commercial and open-source tools answer this with a
ranking, but a ranking is easy to produce and hard to trust: it is unclear what the number
means, what happened to files the tool could not read, and whether two runs on the same
commit produce the same answer.

This report describes **githotmap**, a Python tool that combines Git history with Python
source structure to rank files as *candidates* for inspection. Its distinguishing property is
not the scoring formula — that is deliberately aligned with an existing open-source
implementation so scores remain comparable — but the audit trail around it. Every file the
tool could not fully analyse carries a machine-readable reason code that reaches both the
JSON and the HTML output; a strict mode turns any degradation into a non-zero exit code; and
a canonical serialisation plus SHA-256 fingerprint makes two runs byte-comparable.

We report what was built and what was verified. Two non-functional requirements were frozen
and signed off: robustness/auditability (twelve fault classes, zero crashes, 100 % of
degraded files carrying reason codes) and reproducibility/verifiability (deterministic
serialisation, three frozen snapshots with committed digests, no time source outside an
injected clock). The suite holds 305 passing tests at 92.91 % line coverage over six
platform/Python CI combinations.

The evaluation was reshaped mid-project. A frozen participant study was designed but never
executed; rather than report an unrun experiment, we replaced the ranking-relevance question
(Q2) with a **historical replay** against real commit windows and report its result honestly:
on an iteration-length window the ranked top ten contained substantially more of the files
that later churned than chance would (lift 1.95×), while a deliberately included short-window
counter-run collapsed to 0.94×, which bounds the method's applicability. The interface-effect
question (Q3) is reported as **not answered**.

**Keywords:** technical debt, maintenance prioritisation, Git mining, auditability,
reproducibility, empirical evaluation.

---

## 1. Introduction

### 1.1 The problem we chose

Technical debt is a metaphor that is easy to invoke and hard to operationalise. The literature
offers a rich taxonomy — ten debt types, eight management activities, twenty-nine tools in one
systematic map [P5] — but a maintainer facing a repository on a Monday morning still has to
answer a smaller question: *which file should be opened first?*

Existing tools answer it. CodeCharta visualises a code base as a 3-D city [P4];
[`huangsam/hotspot`](https://github.com/huangsam/hotspot) computes a 0–100 score per file from
Git activity and size; code-maat and churnmap analyse change coupling. What they generally do
not do is make the answer **auditable**. Three failure modes recur:

1. **Silent degradation.** A file with a non-ASCII path, a binary blob, or an unreadable
   permission bit is skipped, receives a score of zero, and appears indistinguishable from a
   genuinely healthy file. The ranking looks complete when it is not.
2. **Unreproducible rankings.** If the analysis timestamp, iteration order, or platform
   line-ending convention leaks into the output, two runs are not comparable, and no
   regression can be detected from a digest.
3. **Scores that overclaim.** A number labelled `roi` invites the reader to believe an
   investment return has been computed. It has not.

These are not hypothetical. In our own Sprint 1 review, a non-ASCII repository path caused
*every* historical metric to collapse to zero with no error at all (defect **M4-2**, reproduced
under test). A tool that silently loses data is worse than no tool, because the team acts on
the result.

### 1.2 Our position

We did not try to invent a better scoring formula. Instead:

- **The scoring semantics are borrowed, deliberately and with attribution.** The `hot`,
  `risk` and `roi` modes — weights, normalisation caps, exponential time decay and debuff
  rules — are aligned with `huangsam/hotspot` (MIT, © 2025 Samuel Huang) at a recorded commit.
  The reason is comparability: a score nobody else's tool would produce is a score nobody can
  cross-check.
- **The fourth mode is ours, and differs on purpose.** `complexity` keeps the name but is
  built from AST structure (cyclomatic complexity, nesting depth, symbol count) plus
  comment-derived self-admitted debt density, because the scan layer that produces those
  signals does not exist in the reference tool.
- **The contribution is the audit layer.** Reason codes, coverage accounting, strict mode,
  deterministic serialisation, fingerprints, and an evaluation contract that was frozen
  before any data was collected.

We state this plainly because it is the honest description: roughly fifteen percent of our
source code implements semantics that correspond to the reference implementation; the rest —
scanner, TODO detection, renderers, diagnostics, clock, evaluation tooling — has no
counterpart there. The relationship is documented item by item in
`docs/research/reference-alignment.md`, and the README declares it.

### 1.3 Contributions

1. **A working tool** (Python CLI + self-contained HTML report + optional Flask entry point)
   that ranks Python files by four activity/structure modes and three composite modes, with
   per-file score breakdowns and natural-language justifications.
2. **An auditable robustness contract (NFR-2).** Twelve frozen fault classes, zero crashes,
   100 % of degraded files carrying a reason code from a single source of truth, coverage
   visible to the reader, and a strict mode that fails the build rather than ship a partial
   result.
3. **A verifiable determinism contract (NFR-3).** One injectable clock, canonical serialisation,
   SHA-256 fingerprints, three frozen snapshots with committed digests, and a two-tier
   cross-platform claim that distinguishes what we control (fixtures) from what we do not
   (arbitrary repositories).
4. **A frozen evaluation contract and a re-shaped evaluation.** When the participant study
   proved infeasible, we replaced one of its three questions with an objective replay method,
   specified and froze the method *before* running it, and report both a positive and a
   negative window.
5. **Process evidence.** Six-member parallel development with per-module ownership, a defect
   register that drove work assignments, formal sign-off on three contested decisions, and a
   whole-repository quality gate in CI.

### 1.4 What this report does not claim

It does not claim the score equals technical debt, defect probability, repair cost, or
financial return. It does not claim the ranking reduces defects or developer time — that would
require the interface study we did not run. It does not claim performance is adequate: a
3,000-file repository takes roughly 14.7 s, the bottleneck is identified, and optimisation was
explicitly excluded from scope. And it does not claim novelty in the scoring formula, which is
attributed above.

### 1.5 Organisation

Section 2 positions the work against the literature. Section 3 states requirements and scope.
Section 4 describes the architecture. Section 5 details the two frozen NFRs. Section 6
reports the software process. Section 7 reports the evaluation. Section 8 discusses threats to
validity. Sections 9 and 10 record relative contributions and individual statements. Section 11
concludes.

---

## 2. Background and Related Work

### 2.1 Technical debt as a management object

P1 frames technical debt as a trade-off between short-term delivery and long-term cost, and
insists on separating the *metaphor* from any specific measurement. That separation is our
first design constraint: the tool speaks of *candidates* and *signals* throughout, never of
confirmed debt.

P5 maps 94 studies (1992–2013) into ten debt types, eight activities — identification,
measurement, prioritisation, representation, communication, monitoring, repayment, prevention
— and 29 tools. Our project occupies a narrow slice: **identification and prioritisation**, on
one artefact type (files), in one language (Python). We deliberately do not attempt
measurement of principal or interest, which P5 shows is where definitions conflict most.

### 2.2 Self-admitted technical debt (SATD)

P2 read 101,762 comments across four projects and derived 62 patterns, reporting that 2.4 %–31.0 %
of files contain SATD candidates. Two lessons shaped our implementation:

- **The reported range is a candidate rate, not a detection accuracy.** We therefore never
  report a TODO ratio as a precision figure.
- **Keywords are entry points, not verdicts.** `# TODO: add dark mode next semester` is a
  product wish; `# TODO: replace this duplicated parser after release` is a debt candidate.
  Our detector surfaces the comment text, path and rule identity, and labels the output
  *SATD candidate* with an explicit "requires human confirmation" clause.

P6 shows that machine learning over accumulated labels substantially outperforms fixed
patterns (10 Java projects, 62,566 classified comments). We did not attempt classification: our
rule set is lexical and therefore has unknown recall. We treat this as a known limitation
rather than a hidden one, and we do not publish a precision claim we cannot support.

Two concrete failure modes we designed against: keyword scanning that does not distinguish
comments from string literals (`message = "FIXME: sample"`), and negation
(`# No workaround is needed after upgrading`). Both are recorded as risks in the research
notes; the first is a false positive we accept, the second a false positive we have not yet
solved.

### 2.3 Churn and change frequency

P3's finding — that *relative* churn measures predict defect density better than absolute
ones — motivated our choice to normalise every metric by a configurable saturation cap rather
than rank on raw magnitudes. It also produced a definitional discipline: P3 distinguishes
churned LOC (added + modified) from deleted LOC, and "lines worked on" as their union. Our
`churn` is `added + deleted` per file over the analysis window, computed from
`git diff --numstat --no-renames`; renames therefore appear as delete + add and inflate churn
for the renamed file. That is a documented distortion, not a silent one.

P3 is a defect-density study on binaries (Windows Server 2003), so it does not validate a debt
score. We cite it for the normalisation argument only.

### 2.4 Visualisation

P4's controlled study of CodeCity (41 analysed of 45 participants) found benefits for
comprehension tasks in a 3-D city metaphor, but the authors had to exclude one unfair task and
four participants. We cite it for two transferable lessons, not for its effect size: a fair
baseline must hold everything constant except the visual variable, and results at class level
in 3-D do not transfer to file level in 2-D. Our own interface study would have tested a
searchable table with versus without a 2-D treemap; it was designed, frozen, and then not
executed (Section 7.5).

We also examined CodeCharta's public sample interactively (v2.5.0): directory search with a
result count, an expandable legend that explains area, height and colour separately, and a
searchable metric menu with definitions. The transferable element was not the 3-D rendering
but **the discipline of explaining what each visual channel encodes** — which we adopted for
our legend.

### 2.5 The reference implementation

`huangsam/hotspot` is a Go CLI that computes four per-file scores (`hot`, `risk`, `complexity`,
`roi`) from Git-derived metrics, plus three composite blends. We used it as a *semantic*
reference and aligned three of the four modes exactly, so that a file scored by both tools
should agree. Our verification snapshot is a fork of the upstream repository at commit
`97b6d8ab` with no local modifications, and the `core/algo/score.go` blob digest matches
upstream `main`.

Where we differ, we differ explicitly (`docs/research/reference-alignment.md`):

| Aspect | Reference | githotmap |
|---|---|---|
| `hot`, `risk`, `roi` weights | 16 weights across 3 modes | identical |
| Normalisation caps | 7 caps | identical, including `log1p` for age |
| Time decay | `hot`/`roi` only, 180-day half-life | identical |
| Debuff rules | test/generate/example/mock, config extensions | identical |
| `complexity` metric set | age, churn, LOC, commits, size, staleness | AST structure + SATD density |
| Score breakdown | components sum to the score | components sum to 100 % (contribution share) |
| Audit layer | none | reason codes, coverage, strict mode, fingerprints |

We do **not** claim to be better than the reference. Two tools agreeing on a number say
nothing about whether the number is right.

---

## 3. Requirements and Scope

### 3.1 Stakeholder and user stories

The primary stakeholder is a maintainer of a Python repository who must decide what to inspect
or refactor next. Seven stories were written in Sprint 1 with acceptance criteria and evidence
links (`docs/sprint-1.md`):

| ID | Story | Priority | Final status |
|---|---|---|---|
| S1-01 | Analyse a local Git repository and rank files | P0 | Delivered (CLI, pipeline, HTML) |
| S1-02 | Machine-readable output for review | P0 | Delivered (JSON renderer, deterministic) |
| S1-03 | Local web page to start analysis and inspect | P0 | Delivered (optional Flask; synchronous, loopback only) |
| S1-04 | File identity and data status survive sorting | P0 | Delivered (path sort, cell↔row link, `missing` not shown as healthy) |
| S1-05 | Requirements, risks and acceptance are traceable | P0 | Delivered (this report and the sprint records) |
| S1-06 | Regression checks run after changes | P0 | Delivered (CI: tests + whole-repo ruff/mypy) |
| S1-07 | Rank with the proposal's C×R baseline | P0 | **Not delivered as specified** |

S1-07 deserves an explicit note. The original proposal called for a frozen
complexity × recency product. The implementation instead uses weighted modes. We did not
retro-fit the story to the code; the record states the deviation and the reason (the weighted
form was needed to reuse the reference implementation's semantics, which the C×R formula would
have discarded). This is recorded as a scope change, not a success.

### 3.2 Choosing non-functional requirements

The course requires at least two non-functional requirements with measurable targets,
architecture and rationale. We chose from three candidates and excluded performance
(Section 3.3).

**Why NFR-2 (robustness and auditability).** A ranking that is silently wrong is worse than no
ranking, because a team will act on it. Our Sprint 1 review produced a concrete instance
(M4-2: non-ASCII paths zeroed all history metrics without an error). Robustness alone — "does
not crash" — would not have caught it. Auditability — "every degradation carries a
machine-readable reason that reaches the reader" — does.

**Why NFR-3 (reproducibility and verifiability).** The course requires a frozen evaluation
contract. Without a deterministic result pipeline, no before/after or cross-tool comparison is
meaningful: observed differences could be clock drift or platform line endings rather than
code change. NFR-3 is therefore the *precondition* for any evaluation at all.

The two are orthogonal: NFR-2 governs what happens when input is bad, NFR-3 governs whether
two runs are comparable.

### 3.3 Non-goals

Stated in the report because a scope without exclusions is not a scope:

| Not done | Reason |
|---|---|
| Performance optimisation (NFR-1) | The course floor was already met; the fix (replacing per-commit reads with a single `--numstat` pass, incremental scanning) would rewrite modules that NFR-3 had just stabilised. A 3,000-file repository takes ~14.7 s; the bottleneck is identified and recorded. |
| Language coverage beyond Python | The scanner contract is language-agnostic, but each parser is real work. Python only, declared. |
| ML-based SATD classification | Requires an annotated corpus (P6 style) we do not have; a lexical rule set with unknown recall is what we ship. |
| Inference from the replay | The replay measures overlap with future churn; it does not measure usefulness to a developer. |
| Participant interface study | Designed and frozen, then dropped for lack of recruitment (Section 7.5). |

---

## 4. Design and Implementation

### 4.1 Layering

The system is a Python package (`src/githotmap`) with a strict top-down dependency graph:

```text
CLI / hosts          cli/main.py            web/app.py (optional)
                     │  orchestrates
Orchestration        core/pipeline.py       (stage guards, timing, degradation tally)
                     │
Sources              core/git.py · core/metrics.py · core/analysis.py
                     scanner/ (walker, parser, scanner)
                     todo/ (parser, detector)
                     │
Model / reasoning    core/scoring.py · core/ranking.py
                     core/models.py · core/diagnostics.py
                     │
Output               renderers/ (base, registry, html, json)   config/config.py
                     │
Cross-cutting        githotmap/clock.py   — depended on by everything, depends on nothing
```

The pipeline is the only component that knows every stage. It runs each stage inside a guard
that records a `stage-failed` degradation plus elapsed time, so that a scanner crash still
yields a report annotated with what was missing, rather than a traceback.

### 4.2 Six load-bearing dependency rules

These are not style preferences. Each rule prevents a failure that already happened in this
repository (`docs/architecture.md` §1.1):

| Rule | The failure it prevents |
|---|---|
| `clock.py` sits at the **top level**, not under `core/` | The scanner needs the clock. If the clock lived in `core/`, importing it would pull `core/__init__` → `scoring` → `models` → `diagnostics` → `scanner`, a cycle. |
| `core/diagnostics.py` must never import `githotmap.config` | Exactly this cycle broke the CLI once (PR #10 regression). |
| `scanner/` imports nothing upward | It is the base of the graph; every consumer joins on its paths and reason codes. |
| Direction is `core → scanner`, never reversed | Diagnostics reuses `scanner.Limitation` as the single reason-code source instead of duplicating literals. |
| `core/pipeline.py` is the only place that knows every stage | Keeps git, scanner, todo and scoring independently testable. |
| Renderers consume `core/models` only | A renderer must not reach into pipeline internals, or format changes start breaking analysis. |

Each rule is guarded by a test, not by convention: `test_clock.py` asserts that no module
outside `clock.py` calls `datetime.now`, `perf_counter` or `time.time` — a repository-wide
source scan, not a spot check.

### 4.3 Metrics

Per file, the pipeline collects:

- **History** (GitPython): commits, churn (`added + deleted`), unique contributors, age in
  days, recent commits/churn within a 90-day window, exponentially decayed commits/churn
  (180-day half-life), and a Gini coefficient of commit distribution across contributors.
- **Size**: bytes, lines of code.
- **Structure** (AST): maximum cyclomatic complexity, maximum nesting depth, symbol count,
  import count.
- **Self-admitted debt**: TODO/FIXME/HACK/XXX occurrences, converted to a density per 1 000 LOC.

All metrics are stored as continuous magnitudes (`float`), not truncated integers, so that
weighting and decay do not introduce clipping artefacts.

### 4.4 Scoring engine

Four base modes, each producing a 0–100 score, a per-signal breakdown and a list of
natural-language justifications:

1. **hot** — recent activity and volatility. commits 0.40, churn 0.40, age 0.10,
   contributors 0.05, size 0.05.
2. **risk** — knowledge concentration / bus factor. inverse-contributors 0.25, Gini 0.25,
   staleness 0.15, age 0.15, size 0.10, LOC 0.05, churn 0.05.
3. **complexity** — structural debt candidates. cyclomatic complexity 0.20, churn 0.20,
   nesting 0.15, LOC 0.15, age 0.10, symbols 0.10, commits 0.05, TODO density 0.05.
4. **roi** — heuristic refactoring priority. churn 0.35, LOC 0.25, Gini 0.25, age 0.15.

Three composite modes blend base scores: `active_owners` (hot 50 + risk 50),
`refactor_now` (complexity 60 + roi 40), `legacy_debt` (complexity 70 + risk 30).

The computation is:

```text
n_x      = clamp(x / cap_x)                     # caps: contrib 20, commits 500,
                                                # size 500 KB, age 3650 d, churn 5000,
                                                # recent 50, LOC 10000
n_age    = clamp(log1p(age) / log1p(3650))      # logarithmic, not linear
final_c  = n_decayed_commits  if mode in (hot, roi) else n_commits
final_ch  = n_decayed_churn   if mode in (hot, roi) else n_churn
score    = 100 × Σ (w_k × n_k)
score   *= 0.75|0.50  if path matches test|generate|example|mock
score   *= 0.50       if extension is configuration-like and mode == complexity
```

Two deliberate departures from the reference implementation:

- **Weights are normalised to sum to 1** before use, so a custom weight set cannot silently
  exceed the 0–100 range.
- **The breakdown reports contribution share, not score components.** In the reference,
  components sum to the score; because the debuff multiplier applies after the weighted sum,
  that identity breaks whenever a file is debuffed. Our breakdown always sums to 100 %, which
  makes the ratios readable and keeps the displayed decomposition consistent with the score.

Severity is a separate, configurable mapping (`critical` ≥ 75, `high` ≥ 50, `medium` ≥ 25),
with two guards not present in the reference: **recency demotion** (a file whose recency signal
is below the low threshold is demoted one grade, so a "historical hotspot" is never presented
as a current one) and **low-confidence status** (fewer than three commits marks the result
`low_confidence` rather than presenting it as a settled conclusion).

Justifications are generated from the breakdown, following the reference's cross-metric
patterns — *Institutional Amnesia* (Gini + age + staleness all significant),
*Volatile Anchor* (dominant churn + significant LOC), *Knowledge Silo* (dominant Gini or
inverse-contributors) — with a fallback that distinguishes "current bottleneck" from
"historical hotspot" using the recency signal against dynamic thresholds.

### 4.5 Scanner and SATD detection

The scanner walks the repository (pruning default-excluded directories), parses each Python
file with `ast`, and emits structure plus a `limitations` list. Critically, the scanner's
`Limitation` enum is the **authoritative reason-code vocabulary**; the core diagnostics layer
references those values rather than redefining them. This single-source rule exists because
duplicating the enumeration is precisely how defect M4-2 remained invisible.

The TODO detector works on comment tokens from `tokenize`, not on raw text, which avoids the
`message = "FIXME: sample"` false positive at the lexical level.

### 4.6 Renderers and hosts

`core` produces `AnalysisResult` without knowing any output format. Renderers implement a
protocol and register themselves. Two ship: a **self-contained interactive HTML** report (no
CDN, no network) and **JSON**. An optional Flask host wraps the same pipeline synchronously
and binds to loopback only.

The HTML report encodes area as LOC and colour as the selected mode's score, with an
explanatory legend that states what each channel means — the one habit we deliberately took
from the CodeCharta observation. Files reported as `missing` are not coloured as healthy.

### 4.7 CLI contract

Exit codes are part of the interface, because CI depends on them:

| Code | Meaning |
|---|---|
| 0 | Analysis completed, no degradations |
| 1 | Analysis failed |
| 2 | Invalid arguments or path |
| 3 | Degradations present and `--strict` was requested |

`--verbose` prints per-stage timing and degradation detail; `--report-coverage` exports the
`AnalysisStats` as JSON so that CI can archive what the tool could and could not read.

### 4.8 One `analyze` run, end to end

The control flow is worth stating explicitly because most of the robustness guarantees live in
it rather than in any single stage:

```text
cli/main.py::_run_analyze
  ├─ validate repo path              → exit 2 if not a directory
  ├─ build ScoringConfig             → --mode / --preset / --exclude / --strict
  └─ AnalysisPipeline(clock).run(repo)
       ├─ _guard("git")       collect commits            → empty/shallow degradations
       ├─ _guard("metrics")   aggregate per-file metrics → commits, churn, gini, decay
       ├─ _guard("scanner")   scan_repository            → AST signals + limitations
       ├─ _guard("todo")      detect SATD                → counts + degradations
       ├─ _guard("scoring")   score_file × N             → scores, breakdown, reasoning
       ├─ rank_files / aggregate_folders
       ├─ tally degradations by (path, code)             ← deduplicated
       ├─ strict check → AnalysisDegradedError (exit 3)
       └─ AnalysisResult(stats=…, analyzed_at=clock.now())
  ├─ --report-coverage → stats as JSON
  ├─ --verbose         → stage timings + remediation hint (stderr)
  └─ renderer          → HTML (default) or JSON
```

Four properties follow from this shape:

1. **No stage can fail silently.** Every stage runs inside a guard that records a
   `stage-failed` degradation together with elapsed time. Even if the scanner dies outright,
   the run still produces a report annotated with what was missing.
2. **Failure is attributable, not just reported.** `result.stats.stage_elapsed_ms` records the
   cost of each stage, so "the analysis was slow" becomes "the git stage took 12.4 s".
3. **Degradation is deduplicated before it is counted.** The scanner and the TODO detector both
   flag the same non-text file; tallying by `(path, code)` instead of by event keeps the
   coverage figure meaningful.
4. **Strictness is checked on the full file set, not the rendered subset.** A file that is
   degraded but falls outside `--limit` still fails the build. This was a real defect: `--strict`
   originally inspected only the ranked output and silently accepted degradations in files the
   user would never see.

The eleven reason codes split into two groups, which reflects the single-source rule of D1:

| Group | Codes | Origin |
|---|---|---|
| File-level, raised by the scanner | `symlink`, `not-text`, `too-large`, `unreadable`, `unsupported-language`, `syntax-error` | `scanner.Limitation` (authoritative) |
| Pipeline/environment, raised by the orchestrator | `git-quotepath`, `stage-failed`, `repo-not-git`, `empty-repo`, `shallow-clone` | `core.diagnostics` extensions |

Each code carries an actionable remediation hint, exposed through `--verbose` and in the report
detail. The hint is deliberately about *what to do*, not about *what went wrong*: telling a user
"this file is binary" is a fact they already knew; telling them "binary files are excluded by
design; remove it from the candidate set or analyse it with another tool" is a decision.

---

## 5. Non-Functional Requirements

### 5.1 NFR-2 — Robustness and auditability

**Statement.** Given arbitrary input (bad encoding, binary files, oversized files, non-ASCII
paths, shallow clones, unreadable files, empty repositories, non-Git directories, corrupt
objects), the tool must not crash and must not degrade silently: every skipped or limited file
carries a machine-readable reason code that reaches the result and the report.

**Measurable acceptance.**

| ID | Metric | Target | How verified |
|---|---|---|---|
| NFR-2.1 | Fault classes that crash the pipeline | **0** | robustness test modules per fault family |
| NFR-2.2 | Degraded files carrying a reason code | **100 %** | `test_scanner_codes.py`, `test_diagnostics_consistency.py` |
| NFR-2.3 | Coverage visible to a reader | matched / emitted / degraded counts plus per-code counts in HTML and JSON | renderer and system tests plus a DOM interaction test |
| NFR-2.4 | `--strict` exit code when any degradation exists | **3**, including when the degraded file falls outside `--limit` | pipeline degradation tests |
| NFR-2.5 | Blind `except` in business code | **0** | ruff `BLE001` / `S110` clean over the whole repository |

The twelve fault classes, **frozen by sign-off**, are: non-ASCII path, binary content,
oversized (> 2 MB), syntax error, declared alternate encoding, symlink, empty repository,
non-Git directory, shallow clone, unreadable file, deep nesting, corrupt Git object.

**Architecture decisions.**

- **D1 — one reason-code source.** `scanner.Limitation` is authoritative;
  `core.diagnostics.DegradationCode` references its values. The rejected alternative was two
  independently maintained enumerations, which is exactly how M4-2 stayed invisible.
- **D2 — dual policy.** Default is best-effort with recorded degradations; `--strict` aborts
  with exit 3 on any degradation. Rejected: always fail-fast (loses the other files' results)
  and always degrade (a CI can pass on a repository it never analysed).
- **D3 — stage guards.** Every stage runs inside a guard recording `stage-failed` plus elapsed
  time. Rejected: silently skipping a failed stage — the Sprint 1 implementation did this
  twice.
- **D4 — deduplicated accounting.** Degradations are tallied by `(path, code)`. Rejected:
  counting events, because scanner *and* TODO both flag the same non-text file, doubling the
  coverage figure.

**Known limits.** Passing fault tests is evidence for the twelve tested classes, not proof of
zero crashes on arbitrary input. Permission behaviour differs under elevated accounts, so
unreadability is exercised through injected I/O failure rather than a real `chmod`. Symlink
scenarios skip on hosts that cannot create links, and skips are recorded as skips.

### 5.2 NFR-3 — Reproducibility and verifiability

**Statement.** For a fixed repository, fixed parameters and a fixed version, two runs produce
the same result apart from explicitly declared non-deterministic fields; a stable digest
identifies that result so regressions are detectable.

**Measurable acceptance.**

| ID | Metric | Target | How verified |
|---|---|---|---|
| NFR-3.1 | Two runs of `canonical()` | byte-identical | determinism test |
| NFR-3.2 | Frozen snapshots with stable digests | **3 snapshots**, stable across re-runs | frozen-fingerprint test |
| NFR-3.3 | Cross-platform behaviour | same digest on both platforms against one committed baseline | CI across six platform/Python combinations |
| NFR-3.4 | Format traceability | `schema_version` present, bumped on format change | determinism test |
| NFR-3.5 | Time sources outside the clock module | **0** | repository-wide source scan in `test_clock.py` |

**Architecture.** An injectable `Clock` protocol with `SystemClock` and `FixedClock`
implementations sits at the package top level; canonical serialisation sorts all collections
and normalises path separators; `fingerprint()` is SHA-256 over the canonical form. Three
synthetic Git snapshots with committed expected digests act as regression anchors.

**Cross-platform equivalence — two tiers, and why the split matters.** The initial sign-off
justified a weak claim ("identical raw digests do not hold on arbitrary repositories") because
Git's working-tree normalisation (`core.autocrlf`) is outside our control. That reasoning is
correct for external repositories. Sprint 3 then showed it was *too* pessimistic for our own
fixtures: once the fixture writer stopped emitting CRLF, digests became identical on Linux and
Windows (CI run #65, commit `ac54bbd`).

Rather than silently strengthen the whole claim, the contract was **split**:

| Tier | Scope | Claim | Enforced by |
|---|---|---|---|
| 1 | Frozen fixtures | identical digest on ubuntu and windows against one committed baseline | CI over six combinations |
| 2 | Arbitrary external repositories | self-consistency and checkout-path independence | determinism and frozen-snapshot tests |

Tier 1 is the stronger claim and is what this report cites. Tier 2 is the honest claim for
inputs we do not control. Nothing in tier 2 was weakened by proving tier 1.

**Known limits.** Identical digests on fixtures do not imply identical results on arbitrary
repositories checked out with different line-ending settings. A `schema_version` bump is
required whenever the format changes, and any change to the fault classes or strict semantics
requires re-sign-off.

### 5.3 Sign-off

Three contested decisions were put to a formal sign-off on 2026-11-21; all three resolved to
option A:

1. **Fault-class denominator** — the twelve classes above, no additions or removals.
2. **Strict-mode semantics** — any degradation is fatal under `--strict`.
3. **Cross-platform equivalence** — two tiers, as above.

Recording these as *team-accepted behaviour* rather than *implemented behaviour* matters: it
means a future change to any of them requires re-sign-off and, where the fingerprint is
affected, a schema version bump. Without that, "the target moved" would be
indistinguishable from "we improved".

### 5.4 The tension between the two NFRs

The two requirements pull in opposite directions, and the resolution is one of the more
interesting parts of the design.

**NFR-2 wants more recording.** Auditability says: capture every degradation, every stage
failure, every elapsed time. The more the tool tells you, the more you can trust what it did.

**NFR-3 wants less variability.** Reproducibility says: two runs must produce the same bytes.
But timing is inherently variable, degradation order can depend on directory traversal order,
and a parallel stage could emit events in a different sequence on a different machine.

A naive combination produces a tool that is either unauditable (drop the detail to stay
deterministic) or irreproducible (keep the detail and lose the digest). We resolved it by
separating **content** from **metadata**:

- Degradations are stored as a set keyed by `(path, code)` and serialised in a fixed sort
  order, so traversal order and duplicate events cannot leak into the output. The *content* of
  the audit is fully deterministic.
- Timing and wall-clock fields are declared non-deterministic in exactly one place.
  `canonical()` strips the declared time fields before hashing, so `analyzed_at` and the
  per-stage elapsed times are visible to a reader but invisible to the fingerprint.
- The declaration is itself tested: `schema_version` is part of the canonical form, so a format
  change is detectable, and a test asserts that two runs of `canonical()` are byte-identical.

The consequence is a rule that generalises beyond this project: **an audit trail must be
deterministic in what it asserts, and explicitly non-deterministic in what it merely observes.**
Elapsed time is an observation; "file X was skipped for reason Y" is an assertion. Mixing them
is what makes a tool either untrustworthy or unversionable.

A second, smaller tension: NFR-3's clock injection means the scanner needs a clock, but placing
the clock inside `core/` creates an import cycle (Section 4.2). The resolution — the clock at
package top level, depending on nothing — is a direct consequence of having taken NFR-3
seriously rather than retrofitted.

---

## 6. Software Process

### 6.1 Sprint structure

The project ran three sprints. Each had a written objective, a deliverable list, and an
explicit exit record.

**Sprint 1 — runnable skeleton and requirements.** Delivered a working CLI, pipeline, scanner,
TODO detector, HTML renderer and JSON renderer, plus seven user stories with acceptance
criteria and architecture proposals for three candidate NFRs. The exit record
(`docs/sprint-1.md`, 2026-11-02) is deliberately unflattering: test counts are reported for the
specific commit and platform they were run on (149 on the baseline, 161 passed and 1 skipped at
`9516f15` on macOS/Python 3.11), the headless browser test is recorded as skipped locally
because Chrome could not start, and the document states that meetings, boards and individual
hours were **not** evidenced in the repository and were not reconstructed.

**Sprint 2 — the two NFRs.** Implemented NFR-2 (diagnostics model, degradation propagation,
strict mode, fault-injection suite, coverage panel) and NFR-3 (deterministic serialisation,
fingerprints, injectable clock, frozen fixtures), closed the code-quality baseline (whole-repo
ruff and mypy at zero, CI gates on six combinations), and froze the evaluation contract. Three
contested decisions were signed off at close.

**Sprint 3 — hardening, diagnostics, evaluation, delivery.** Added the performance regression
guard, fixed the cross-platform line-ending defect that had blocked tier-1 equivalence,
resolved the flaky-test investigation, added `--verbose` and `--report-coverage`, completed the
contract index, executed the evaluation, and produced the deliverables.

### 6.2 Organisation and ownership

Six members with module ownership, explicit work packages and an estimate of 78 person-hours
for the NFR sprint:

| Member | Role | Primary work |
|---|---|---|
| M1 | PM / requirements | NFR scope document, evaluation contract, sign-off closure |
| M2 | Scanner | injectable clock, three frozen fixtures with expected digests |
| M3 | TODO detection | detector degradation handling, symlink skip |
| M4 | Git history | quotepath fix and regression tests, seven `Repo` leaks closed |
| M5 | Scoring / pipeline | diagnostics model, degradation propagation, strict mode, deterministic serialisation |
| M6 | Dashboard / tests | fault-injection suite, coverage panel, CI gates |

The critical path was `diagnostics model → degradation propagation → strict mode`, all owned by
one member, which made that member the bottleneck. The mitigation — freezing the diagnostics
interface first so the dashboard could be built in parallel — is the kind of scheduling decision
that only matters because the dependency was made explicit early.

### 6.3 Defect management and what it changed

A defect register was maintained as a working document rather than a retrospective one. Two
entries materially changed the design:

**M4-2 — non-ASCII paths silently zeroed all history metrics (P0, reproduced under test).**
`git`'s default `core.quotepath=true` returns non-ASCII paths quoted and octal-escaped; the
path strings therefore never matched the scanner's paths, and every history metric fell to
zero with no error. This was not a crash — the tool produced a complete, plausible, entirely
wrong report. The response was structural, not local: a single authoritative reason-code
vocabulary (D1 in Section 5.1), a regression test that asserts the specific failure, and a
project rule that degradation must be *recorded*, never inferred from a zero.

**PR #10 — a merge that silently lost work.** A pull request replaced `core/scoring.py` with an
older structure, dropping 22 tests and reintroducing a circular import that broke the CLI. The
recovery restored the newer structure and ported the intended features forward. The process
change was a whole-repository `ruff` + `mypy` gate in CI and a contract index
(`docs/architecture.md` §2) recording, for each invariant, which document defines it and which
test would fail if it drifted.

Two further defects were found during the NFR work and are worth naming because they were
*reporting* defects rather than computation defects: `degradations_by_code` was always empty,
and `--strict` missed degradations for files outside `--limit`. Both meant the tool's own
account of its health was wrong while its numbers were right — which is exactly the failure
mode NFR-2 exists to prevent.

### 6.4 Quality gates

Every push and pull request runs:

- the full test suite on **six** combinations (ubuntu/windows × Python 3.10/3.11/3.12), plus a
  separate slow-marked performance job on one combination;
- **whole-repository** `ruff` and `mypy` (not only changed files), with pinned tool versions;
- a coverage gate at `fail_under = 90`.

Current state on `main`: **305 passed, 8 skipped, 3 deselected** (slow), **92.91 % line
coverage** (1952 of 2101 statements), zero ruff findings, zero mypy findings. The repository
holds 4 231 lines of source across 34 files and 3 775 lines of tests across 33 files, built
over 117 commits.

The eight skips are platform-conditional (symlink creation, headless browser availability) and
are recorded as skips rather than silently passing — the same discipline the NFR contract
requires of the tool itself.

### 6.5 What the process records can and cannot show

The repository can reconstruct: commit history, pull requests, CI runs, test and coverage
numbers, the frozen contracts, and the sign-off sheets. It cannot reconstruct: meeting
attendance, individual hours, or work done outside version control. We have not filled those
gaps with estimates presented as records. This distinction is stated in the Sprint 1 record and
should be preserved in any presentation of the project's "process evidence".

### 6.6 Version control and review practice

The team used a single long-lived `main` protected by CI, with short-lived feature branches
merged back through `--no-ff` merges, so that each unit of work remains a visible, revertable
island rather than a linear smear of small commits.

Three practices did real work rather than decorating the history:

**Commit messages carry a work-package identifier.** A message such as
`feat(eval): historical replay script; Q2 switched to replay (WP-S3-4)` makes it possible to
answer "who did this and why" months later, and it is what allowed this report's process
section to be written from the repository rather than from memory.

**Contracts live in documents, and the index points to the tests.** `docs/architecture.md` §2
records, for each invariant, which document defines it, who consumes it, and which test would
fail if it drifted. Without that index a reviewer has to guess which of 33 test modules guards
which promise.

**Every quality claim is a CI run, not an assertion.** Coverage percentages, platform
combinations and lint results in this report are quoted from named runs; where a number could
only be obtained locally, the report says so.

The counterexample is instructive. The PR #10 back-merge (Section 6.3) happened because review
focused on the *intent* of the change ("port the new features forward") without a gate that
would catch the destructive *effect* (22 tests silently deleted, a circular import
reintroduced). The fix was not more careful review — careful review had already failed — but a
whole-repository gate that runs on every push, regardless of what the author believed they had
changed. The general lesson is that **review catches intent; only automated gates catch
effect.**

---

## 7. Evaluation

### 7.1 Why the evaluation was restructured

The evaluation contract was frozen on 2026-11-20 with three separate questions:

| ID | Question | Intended instrument |
|---|---|---|
| Q1 | Data correctness — does the tool compute what it claims? | automated tests |
| Q2 | Candidate relevance — is the ranking a meaningful worklist? | manual review of high-score files |
| Q3 | Interface effect — does the file map help a reader decide? | controlled participant study |

The participant study (Q3, which also carried the Q2 review) required recruiting 8–12 people.
It was designed in full — four frozen tasks, two datasets, a Latin-square arm/dataset
balancing, answer keys computed from frozen snapshots before any session, anti-tampering
clauses — and then **not executed**: recruitment did not happen.

Two options were available. Invent numbers, or report nothing. We took a third: **keep Q3 as an
unanswered question and replace Q2's instrument with an objective method that requires no
participants.**

The contract was therefore amended to **v1.1** on 2026-11-23, with the amendment recorded in
the contract itself, split into separate sections, and justified in writing:

- Q1 is unchanged and remains covered by the test suite.
- Q2 is answered by **historical replay** (Section 7.3).
- Q3 is marked **dropped, not executed**. Its frozen tasks are retained verbatim so a future
  cohort could revive it, but no result of any kind may be reported for it.

Amending a frozen contract is exactly the move the contract's own anti-tampering clauses exist
to police, so the reason for the amendment must be stated plainly: **the change was made
before any Q2 result existed, not after seeing an unfavourable one.** The replay method,
its metric definitions, its sample-size guards and — critically — its window-selection rule
were specified and frozen *first*, and the results were produced afterwards.

### 7.2 Q1 — Data correctness

Covered by the suite. Evidence relevant to the claim:

- twelve fault classes exercised with zero pipeline crashes (NFR-2.1);
- 100 % of degraded files carrying a reason code, asserted across scanner and pipeline
  (NFR-2.2);
- score-boundary and breakdown-invariant tests; the breakdown is asserted to sum to 100 %;
- double-run identity of `canonical()` (NFR-3.1);
- three frozen snapshots with committed digests, identical on both platforms (NFR-3.3);
- 92.91 % line coverage with a 90 % gate.

Q1 is the strongest of the three claims, and it is still bounded: tests confirm that the tool
computes what it says it computes, not that the computation is a good model of technical debt.

### 7.3 Q2 — Method: historical replay

**The problem with asking humans.** Manual review of high-score files is opinion about a
ranking. It is slow, subjective, and — with a six-person team reviewing its own tool — openly
biased.

**The replacement.** Score the repository as it stood at commit *t0*, then look at what the
next window of commits actually touched. No participants, no annotation, and anyone can rerun
it.

Procedure (frozen):

1. Resolve `t0` and `t1`, requiring `t0` to be a strict ancestor of `t1`.
2. Materialise a detached worktree at `t0` and run the normal analyser on it, producing scores
   exactly as a user would have seen them at that moment.
3. Sum per-file churn over `t0..t1` from `git diff --numstat --no-renames`.
4. Define `comparable` = files that were scored at `t0` **and** changed in the window. Files
   created after `t0` cannot be scored; files deleted in the window are listed separately.
   Neither enters `comparable`.
5. Compare the tool's top-K by score against the top-K of `comparable` by churn.

**Metrics, and which one is primary.** Precision@K is intuitive but misleading here: if a
window touches most of the repository, Precision approaches 1 for *any* ranking. We therefore
report the random baseline `|comparable| / |scored|` and make **lift = Precision / baseline**
the primary metric. Recall@K measures whether the flag set contained the heaviest files, and
Spearman ρ measures whether score magnitude orders churn correctly.

**Sample-size guards (frozen).** With `comparable < 2K` the run emits a warning and the result
must not be stated as a conclusion. With `comparable < K`, Precision cannot exceed
`comparable / K` and a low value does not by itself indicate bad ordering. With zero
comparable files the run aborts.

**Window-selection rule (frozen to prevent cherry-picking).** The primary window is the span
from the **Sprint 1 final tag** (`daf9500`, tagged `sprint1-final`, 2026-11-07) to `HEAD` — all
of Sprint 2 plus most of Sprint 3, roughly 16 days. The sensitivity window is the shortest
available (`HEAD~8..HEAD`), and its purpose is to expose the method's failure mode — not to be
discarded if it looks worse. Any additional window must be justified by a rule stated in
advance, never by its result.

### 7.4 Q2 — Results

**Primary window** (`daf9500..HEAD`, 48 commits over 15.9 days, 65 files scored, 60 changed,
30 comparable, 0 deleted):

| Metric | Value |
|---|---|
| Precision@10 | **90.0 %** (9/10) |
| Random baseline | 46.2 % (4.6/10) |
| **Lift** | **1.95×** |
| Recall@10 | 50.0 % |
| Spearman ρ | 0.2262 |

The headline is not 90 %. With 30 of 65 scored files touched in the window, a blind pick hits
46 %; the tool roughly doubled the hit rate of chance. Recall of 50 % is the honest weakness:
the two heaviest-churn files in the window (`core/pipeline.py`, 344 changed lines;
`core/analysis.py`, 214) were **not** in the top ten. The tool preferred historically hot files
that were quiet in this particular window over the files actually being rewritten. And
ρ = 0.226 means the *set* is reasonable while the *order within it* is not.

**Sensitivity window** (`HEAD~8..HEAD`, 15 commits over 1.9 days, 85 scored, 19 changed,
9 comparable):

| Metric | Value |
|---|---|
| Precision@10 | 10.0 % (1/10) |
| Random baseline | 10.6 % (1.1/10) |
| **Lift** | **0.94×** |
| Recall@10 | 10.0 % |
| Spearman ρ | 0.05 |

**This run is reported as a failure, not omitted.** It triggered both guards
(`9 < 2×10`, and `9 < 10`, capping attainable Precision at 90 %). Nine of the tool's top ten
files had zero churn in the window: this window edited documentation and evaluation scripts
under a directory that did not exist at `t0`.

The two runs together support one claim and refute a stronger one:

- **Supported:** over an iteration-length window of real product work, the flag set contains
  substantially more of the actually-churned files than chance does (lift 1.95×).
- **Refuted:** that the score orders future churn reliably (ρ ≈ 0.23; the two heaviest files
  outside the top ten), or that the method generalises across window lengths (0.94× below one
  iteration, with the window's work concentrated in non-product files).

The failure is informative rather than embarrassing: it establishes the method's precondition
explicitly — **the window must span at least one iteration and must contain product code**.

### 7.5 Q3 — Reported as not answered

The interface question — does the file map help a reader decide? — remains open. It is
reported as open, not as "partially supported", and not by proxy through the replay. The replay
measures whether a flag set overlaps future churn; it says nothing about comprehension speed,
decision quality, or whether a visual encoding helps anyone.

The tool's interface choices (treemap encoding area as LOC and colour as score, an explicit
legend, a searchable table) are motivated by the literature and by the CodeCharta observation.
They are not validated by our own measurement, and this report does not claim otherwise.

### 7.6 What the evaluation does and does not establish

| Claim | Status |
|---|---|
| The tool computes what it documents (Q1) | Established for the tested inputs |
| On an iteration-length window, the ranking's top ten overlaps future churn about twice as often as chance | Established on one repository, descriptively |
| The ranking orders future churn reliably | **Not** established |
| The method works on short windows or non-product work | **Refuted** by the sensitivity run |
| The interface improves comprehension or decisions | **Not answered** |
| Acting on the ranking reduces defects, effort or cost | Not tested, and not implied |

All figures are descriptive. No inferential test is reported because the comparable set is 30
files from a single repository over a single window; a p-value would add false precision.

### 7.7 Generality of the replay method

The method is not novel and should not be presented as such. Retrospective evaluation — score a
system at time *t*, observe what happened afterwards — is long established in empirical
software engineering, and it is the natural way to test any tool whose output is a prediction
about future work. P3's relative-churn predictors were validated on a future release in
exactly this spirit.

What we can claim is a **specification** of how to run it without fooling yourself, and that
specification is transferable to any tool that ranks files:

1. **Fix the comparison set before scoring.** `comparable` must be defined by the data (scored
   *and* changed), not adjusted after seeing which files the tool picked. Files created after
   *t0* cannot be scored and files deleted in the window cannot be assessed; both must be
   excluded *and reported*, because silently dropping them inflates every ratio.
2. **Report the random baseline, always.** Precision alone is meaningless when the window
   touches most of the repository. Lift is the only figure that survives a busy window.
3. **Guard the sample size.** Below `2K` comparable files the numbers become direction-only;
   below `K`, Precision has a hard ceiling that has nothing to do with ordering quality.
4. **Fix the window rule in advance.** This is the single most important line of defence
   against self-deception: a team that chooses its window after seeing results can always find
   a flattering one. Our primary window was written into the contract before the tool existed in
   its current form, and the unfavourable sensitivity window was reported because the rule said
   so.
5. **Expect the method to fail on short windows.** Historical activity signals update on the
   order of weeks. A window shorter than one iteration measures task assignment, not code
   health, and will produce lift near or below 1 for a perfectly reasonable tool.

Two things the method cannot do, and which no amount of window tuning will fix: it cannot
measure whether a *developer* benefits (that needs an interface study), and it cannot separate
"the tool is good" from "the tool is scored on a repository whose authors happen to be busy in
predictable places". The second is why replication on unfamiliar repositories is future work
rather than a formality.

---

## 8. Threats to Validity

### 8.1 Construct validity — are we measuring the right thing?

The central construct threat is that **a high score is a candidate signal, not debt**. Nothing
in this project validates the score against a ground truth of remediation cost, defect density,
or maintainer judgement. The names invite over-reading and we have tried to neutralise that in
the tool itself: `complexity` is documented as a composite and not a cyclomatic value, `roi` is
documented as a heuristic and not a measured return, and every justification ends in
"candidate, needs human confirmation".

The replay has its own construct gap: it measures **overlap with future churn**. Churn is a
proxy for maintenance attention, not evidence of debt. A file can churn heavily because it is
healthy and actively developed. We therefore describe the result as predictive overlap and
never as accuracy, usefulness, or debt detection.

### 8.2 Internal validity

- **The analyser at `t0` is today's analyser.** The replay checks out an old *snapshot* but
  runs the *current* scoring code. This is intentional — we are evaluating the tool, not the
  history — but it means the result characterises the tool as of the recording commit, not as
  of `t0`.
- **Rename handling.** `--no-renames` turns a rename into a delete plus an add, inflating churn
  for the new path. This was rare in the analysed windows (zero deletions) but is a systematic
  bias, not a rounding error.
- **Churn is unweighted by file kind.** A busy generated file or documentation page counts the
  same as logic. Restricting to source paths would be more faithful; it was not done.
- **A single window, a single repository.** The primary result rests on 30 comparable files.
  Any generalisation beyond that is unsupported.

### 8.3 External validity

- **One language.** Only Python files are structurally parsed. Git-only modes work on any
  repository, but `complexity` requires the AST layer.
- **One repository, and it is ours.** This is the most serious threat and it deserves stating
  without softening: the replay was run on the team's own repository, by the team that wrote
  the tool. A tool whose authors know which files were being edited may encode that knowledge
  in its defaults without intending to. Mitigations are partial — the windows were fixed by
  rule before the results existed, the sensitivity window was reported despite being
  unfavourable, and the scoring semantics come from an external reference rather than our
  taste — but they do not remove the conflict of interest. An independent replication on
  repositories the team has never seen is the correct remedy and has not been performed.
- **Convenience sampling of everything.** The repository, the window and the thresholds are all
  choices of convenience. None is a random sample of anything.

### 8.4 Reliability and reproducibility

The tool itself is reproducible by construction (Section 5.2): canonical serialisation, fixed
clock, committed digests, identical results on both platforms for the frozen fixtures. The
*evaluation* is reproducible in the weaker sense that the command and parameters are recorded;
its result still depends on the window, which the contract fixes by rule rather than by
construction.

### 8.5 Summary of what may and may not be claimed

| May be claimed | May **not** be claimed |
|---|---|
| The tool computes what it documents, for the tested inputs | The tool identifies technical debt |
| Degradation is never silent; coverage is visible | The tool never fails on untested input |
| Two runs on a fixed input are byte-identical | Any two repositories produce comparable scores |
| On an iteration-length window of this repository, top-10 overlap with future churn was about twice chance | This ranking improves maintenance outcomes |
| The ranking's internal ordering is weak (ρ ≈ 0.23) | — |
| The interface question is open | The interface helps or does not help |

### 8.6 Implications for practitioners

Six things we would tell a team starting the same project, all of them learned the hard way.

**1. Make degradation a first-class output before you make the report pretty.** The temptation
is to build the visualisation first, because it is what stakeholders see. But a report that
cannot say what it failed to read is a liability: it is confidently incomplete. In our case the
audit layer had to be retrofitted through the pipeline (NFR-2), touching every stage, after the
renderer already existed.

**2. One reason-code vocabulary, or none.** Two enumerations that are *supposed* to agree will
diverge, and the divergence is invisible because each side is internally consistent. This is
exactly how a non-ASCII path silently zeroed every history metric. The fix is not discipline;
it is a rule that one enum is authoritative and the other references its values.

**3. Freeze the evaluation before you have results, and write the freeze down.** A contract that
lives in someone's head is not frozen. Ours is a file, with a version number, with an amendment
procedure, and with the window-selection rule written into it *before* the first run. That is
what made it possible to report an unfavourable window without appearing to cherry-pick.

**4. Prefer an objective instrument over an inconvenient one you cannot run.** We designed a
full participant study and never executed it. Keeping it as the only instrument would have left
the project with no evaluation at all. Replacing one question with a replay — while leaving the
other explicitly unanswered — is a better outcome than a frozen plan that produces nothing.

**5. Report the failure case.** The short-window run (lift 0.94×) is the most useful result we
have, because it defines the method's precondition. A report with two favourable windows would
have been less informative and less credible.

**6. Align with a reference implementation and say so.** Borrowing the scoring semantics made
our numbers cross-checkable and saved us from inventing thresholds with no basis. It also
forced an exact account of what is shared and what is ours. Trying to appear more original
would have made the tool less comparable and the report less honest.

Two anti-patterns worth naming, both of which we committed and had to undo:

- **Retro-fitting the requirement to the implementation.** Story S1-07 specified a C×R formula;
  the implementation used weighted modes. It would have been easy to rewrite the story and call
  it delivered. The record keeps the deviation visible instead.
- **Trusting a green build as acceptance.** Passing tests meant the code did what the tests
  asserted, not that the team had accepted the behaviour. That is why three contested decisions
  went through a formal sign-off sheet rather than being settled by whichever member wrote the
  code.

---

## 9. Relative Contributions

Contributions are recorded by module ownership and by the work packages each member owned.
Percentages are deliberately not invented; the team's signed contribution statement should
carry whatever figures the team agrees on, and this section supplies the evidence base for it.

| Member | Owned modules / work packages | Visible evidence in the repository |
|---|---|---|
| **M1** | Requirements, NFR scope, evaluation contract, sign-off closure | `docs/sprint-1.md`, `docs/nfr.md`, `docs/evaluation-contract.md` (v1.0 and v1.1), sign-off sheets |
| **M2** | Scanner, injectable clock, frozen fixtures | `scanner/`, `clock.py`, three frozen snapshots and committed digests, `test_clock.py`, `test_frozen_fingerprints.py` |
| **M3** | TODO detection | `todo/`, detector degradation handling, symlink handling |
| **M4** | Git history analysis | `core/git.py`, `core/analysis.py`, quotepath fix and regression test, resource-leak fixes |
| **M5** | Diagnostics, pipeline, scoring | `core/diagnostics.py`, `core/pipeline.py`, `core/scoring.py`, strict mode, deterministic serialisation |
| **M6** | Dashboard, test suite, CI | `renderers/html.py`, `web/`, fault-injection suite, coverage panel, `.github/workflows/tests.yml` |

Cross-cutting work that does not map to a single owner: the evaluation replay tooling, the
contract index, the README and research documentation, and the Sprint 3 quality hardening.

*Estimated* effort for the NFR sprint (from the plan, not a measurement of actual hours):
M1 10 h, M2 14 h, M3 9 h, M4 11 h, M5 18 h, M6 16 h — approximately 78 person-hours. The plan
notes that M5's serial critical path made that member the bottleneck.

---

## 10. Individual Profiles and Contribution Statements

> **Placeholders.** The repository records GitHub account names, not personal names, roles or
> bios. Nothing below is invented; each block must be completed by the member concerned. The
> per-member *evidence* is in Section 9 and should be cited rather than restated.

**M1 — `[Name]`.** Project management and requirements; NFR scope and evaluation contract;
sign-off coordination.
*Contribution statement:* `[to be written by M1, covering requirements, sprint coordination,
documentation and the evaluation contract, with module evidence above.]`

**M2 — `[Name]`.** Scanner; injectable clock (NFR-3); frozen fixtures and expected digests.
*Contribution statement:* `[to be written by M2.]`

**M3 — `[Name]`.** TODO / SATD detection.
*Contribution statement:* `[to be written by M3.]`

**M4 — `[Name]`.** Git history analysis; non-ASCII path fix.
*Contribution statement:* `[to be written by M4.]`

**M5 — `[Name]`.** Diagnostics model, degradation propagation, strict mode, deterministic
serialisation.
*Contribution statement:* `[to be written by M5.]`

**M6 — `[Name]`.** Dashboard, fault-injection suite, CI gates.
*Contribution statement:* `[to be written by M6.]`

---

## 11. Conclusion and Future Work

We built a tool that ranks files as candidates for inspection, and — more importantly — one
that says out loud what it could not read. The scoring formula is borrowed and attributed; the
audit layer is ours. Two non-functional requirements were frozen, implemented and signed off,
and the whole repository is guarded by a six-combination CI matrix with a 90 % coverage floor.

The evaluation is the least comfortable part of this report, and it is reported that way on
purpose. One question is answered with moderate, honestly bounded evidence (lift 1.95× on an
iteration-length window), one is answered in the negative (the ranking does not order future
churn reliably), one is answered with an explicit failure (lift 0.94× below one iteration), and
one is not answered at all (the interface effect). We believe this is more useful than a
uniformly positive result, because the boundaries are now known: the method needs a window of
at least one iteration containing product code, and it must not be described as measuring
usefulness.

**Future work, in priority order:**

1. **Run the interface study.** Q3 is designed, frozen and unanswered. It is the single largest
   gap in the evidence, and the only one that cannot be closed by better tooling.
2. **Replicate the replay on repositories the team does not own.** This is the direct remedy
   for Section 8.3's conflict of interest.
3. **Restrict churn to source paths** and re-run both windows, to test whether the ρ ≈ 0.23
   ordering weakness is partly a measurement artefact.
4. **Performance.** Replace per-commit GitPython reads with a single `--numstat` pass and add
   incremental scanning; the bottleneck is already identified and measured at ~14.7 s for
   3,000 files.
5. **Additional language parsers**, which the contract already permits.
6. **Enable or remove the unused `imports` signal** in `complexity` — currently computed,
   weighted at zero, and therefore inert. Recorded rather than silently fixed, because
   changing it would invalidate the frozen digests.

---

## References

[P1] P. Kruchten, R. L. Nord, I. Ozkaya. "Technical Debt: From Metaphor to Theory and
Practice." *IEEE Software*, 29(6):18–21, 2012.

[P2] A. Potdar, E. Shihab. "An Exploratory Study on Self-Admitted Technical Debt." *ICSME*,
2014. DOI: 10.1109/ICSME.2014.31.

[P3] N. Nagappan, T. Ball. "Use of Relative Code Churn Measures to Predict System Defect
Density." *ICSE*, 2005.

[P4] R. Wettel, M. Lanza, R. Robbes. "Software Systems as Cities: A Controlled Experiment."
*ICSE*, 2011:551–560. DOI: 10.1145/1985793.1985868.

[P5] Z. Li, P. Avgeriou, P. Liang. "A systematic mapping study on technical debt and its
management." *Journal of Systems and Software*, 101:193–220, 2015.
DOI: 10.1016/j.jss.2014.12.027.

[P6] E. da S. Maldonado, E. Shihab, N. Tsantalis. "Using Natural Language Processing to
Automatically Detect Self-Admitted Technical Debt." *IEEE Transactions on Software
Engineering*, 43(11):1044–1062, 2017. DOI: 10.1109/TSE.2017.2654244.

[REF] `huangsam/hotspot` — open-source Go CLI for Git hotspot analysis, MIT License,
© 2025 Samuel Huang. <https://github.com/huangsam/hotspot>. Verification snapshot:
commit `97b6d8ab`, unmodified; `core/algo/score.go` blob digest matches upstream `main`.

[CC] CodeCharta, v2.5.0 public sample. <https://codecharta.com/visualization/app/>
(observed 2026-09-20).

---

## Appendix A — Repository artefacts referenced in this report

| Artefact | Path |
|---|---|
| Architecture, layering, contract index | `docs/architecture.md` |
| NFR scope, acceptance, sign-off | `docs/nfr.md` |
| Evaluation contract (v1.1) | `docs/evaluation-contract.md` |
| Evaluation results and threats | `docs/evaluation-replay-result.md` |
| Reference-implementation alignment | `docs/research/reference-alignment.md` |
| Literature review (P1–P6) | `docs/research/literature-review.md` |
| Tool comparison and CodeCharta observation | `docs/research/tool-comparison.md` |
| Sprint 1 record | `docs/sprint-1.md` |
| Development and submission workflow | `CONTRIBUTING.md` |
| Replay tool | `examples/evaluation/historical_replay.py` |
| Frozen digests | `tests/fixtures/frozen_fingerprints.json` |




