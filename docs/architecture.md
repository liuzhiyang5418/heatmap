# Architecture and contract index

Two things live here: (1) how the package is layered and which dependency directions are
**load-bearing**, and (2) an index of every cross-module contract — what defines it, who
consumes it, and which test would fail if it silently drifted.

If you are about to change a data structure, a reason code, or a serialisation rule, read §2
first: the module you "just" want to touch may be on the wrong side of a one-way edge.

---

## 1. Layering

```text
                      ┌──────────────────────────────────────────────┐
   CLI / hosts        │  cli/main.py        web/app.py (optional)    │
                      └───────────────┬──────────────────────────────┘
                                      │  orchestrates
                      ┌───────────────▼──────────────────────────────┐
   Orchestration      │  core/pipeline.py                            │
                      │  (stage guards, timing, degradation tally)   │
                      └───┬───────────┬───────────┬──────────┬───────┘
                          │           │           │          │
        ┌─────────────────▼──┐  ┌─────▼─────┐  ┌──▼───────┐  │
        │ core/git.py        │  │ scanner/  │  │ todo/    │  │
        │ core/metrics.py    │  │ walker    │  │ parser   │  │
        │ core/analysis.py   │  │ parser    │  │ detector │  │
        └─────────┬──────────┘  │ scanner   │  └────┬─────┘  │
                  │             └─────┬─────┘       │        │
                  │                   │             │        │
        ┌─────────▼───────────────────▼─────────────▼────┐   │
        │ core/scoring.py   core/ranking.py              │◄──┘
        │ core/models.py    core/diagnostics.py          │
        └─────────┬──────────────────────────────────────┘
                  │
        ┌─────────▼──────────┐        ┌────────────────────┐
        │ renderers/         │        │ config/config.py   │
        │ base · registry    │        │ weights · presets  │
        │ html · json        │        └────────────────────┘
        └────────────────────┘

        githotmap/clock.py  ── depended on by everything, depends on nothing
```

### 1.1 Load-bearing dependency rules

These are not style preferences — each one prevents a concrete failure that already happened
or would recur.

| Rule | Why | Guarded by |
|---|---|---|
| `clock.py` sits at the **top level**, not under `core/` | `scanner` needs the clock; if it lived in `core/`, importing it would pull in `core/__init__` → `scoring` → `models` → `diagnostics` → `scanner`, a cycle | `test_clock.py` import smoke + CI |
| `core/diagnostics.py` must **never** import `githotmap.config` | `config → core.metrics → core/__init__ → core.diagnostics` would close a loop; this exact cycle broke the CLI once (PR #10 regression) | module docstring + `test_clock.py`, `test_diagnostics.py` |
| `scanner/` must not import anything upward | It is the base of the graph; every consumer joins on its paths and codes | `test_scanner_*` run standalone |
| Direction is `core → scanner`, never the reverse | `diagnostics` reuses `scanner.Limitation` as the single reason-code source | `test_diagnostics_consistency.py` |
| `core/pipeline.py` is the only place that knows every stage | Keeps `git`/`scanner`/`todo`/`scoring` independently testable | `test_pipeline_degradation.py` |
| Renderers consume `core/models` only | A renderer must not reach into pipeline internals | `test_html.py`, `test_json_renderer.py` |

---

## 2. Contract index

Every row is a promise one module makes to another. The "locked by" column names the test that
fails if the promise quietly changes — **if you edit a contract, that test is where you look
first.**

### 2.1 Data-format contracts

| Contract | Canonical doc | Defined by | Consumed by | Locked by |
|---|---|---|---|---|
| **Repository-root-relative POSIX paths**, no `./` prefix, `core.quotepath=false` | `docs/scanner-interface.md` §4.1 | M2 scanner | M3 / M4 / M5 / M6 (dictionary join) | `test_scanner_api.py`, `test_scanner_codes.py`, `test_git.py::test_git_history_preserves_non_ascii_paths` |
| **Reason codes — single source of truth** (`scanner.Limitation`, `LIMITATION_CODES`) | `docs/scanner-interface.md` §4.5 | M2 scanner | `core/diagnostics.DegradationCode` | `test_scanner_codes.py`, `test_diagnostics_consistency.py` |
| **`FileStructure` / `ScanStats` / `RepositoryScan`** fields and invariants | `docs/scanner-interface.md` §5 | M2 scanner | M3 / M5 / M6 | `test_scanner_api.py`, `test_scanner_parser.py` |
| **TODO detection output** (`TodoScan`, ordering by `(path, lineno, column)`) | `docs/todo-interface.md` | M3 todo | M5 pipeline | `test_todo_parser.py`, `test_todo_detector.py`, `test_todo_robustness.py` |
| **Git collection** (`CommitRecord`, `GitCollectResult`, empty/shallow degradation) | `docs/git-interface.md` | M4 git | M5 pipeline | `test_git.py`, `test_git_robustness.py`, `test_analysis_robustness.py` |

### 2.2 Behavioural contracts

| Contract | Canonical doc | Defined by | Consumed by | Locked by |
|---|---|---|---|---|
| **Degradation propagation** — every skip carries a machine-readable code that reaches the result | `docs/nfr.md` §2.3 (D1–D4) | M5 pipeline | CLI, HTML/JSON | `test_diagnostics.py`, `test_pipeline_degradation.py` |
| **Degradation accounting is deduplicated by `(path, code)`** | `docs/nfr.md` §2.3 (D4) | M5 pipeline | coverage panel | `test_diagnostics_consistency.py::test_degradation_counts_are_not_double_counted` |
| **`--strict` = any degradation is fatal** (exit 3, even outside `--limit`) | `docs/nfr.md` §7 (decision 2) | M5 pipeline + CLI | CI users | `test_pipeline_degradation.py`, `test_nfr2_system.py`, `test_cli_smoke.py` |
| **Reason code → remediation hint** (every code has an actionable one) | `core/diagnostics.py` `REMEDIATION_HINTS` | M2/M5 | CLI `--verbose`, `--strict` output | `test_cli_diagnostics.py::test_every_degradation_code_has_a_hint` |
| **Exit-code contract**: 0 ok / 1 analysis failed / 2 config or format / 3 strict | `cli/main.py` docstring | CLI | scripts, CI | `test_cli_smoke.py` |

### 2.3 Determinism contracts (NFR-3)

| Contract | Canonical doc | Defined by | Consumed by | Locked by |
|---|---|---|---|---|
| **Single injectable clock**; no `datetime.now` / `perf_counter` / `time.time` elsewhere | `docs/nfr.md` §3.3 (D1) | M2 (M2-owned module) | core, scanner | `test_clock.py::test_time_sources_are_confined_to_clock_module` |
| **`canonical()`** drops clock + host identity, sorts keys, `round(6)`, normalises separators | `docs/nfr.md` §3.3 (D2) | M5 models | evaluation, regression | `test_determinism.py` |
| **`fingerprint()`** = SHA-256 of canonical bytes; **one baseline, both platforms** (tier 1) | `docs/nfr.md` §3.3 (D4/D5) + §7.1 | M5 models | CI cross-platform gate | `test_frozen_fingerprints.py::test_fingerprints_match_committed_baseline` |
| **Self-consistency + checkout-path independence** for arbitrary repos (tier 2) | `docs/nfr.md` §7.1 | M5 | evaluation | `test_frozen_fingerprints.py` (other two cases) |

### 2.4 Process / acceptance contracts

| Contract | Canonical doc | Owner | Notes |
|---|---|---|---|
| **NFR scope, metrics, exclusions, confirmed decisions** | `docs/nfr.md` (esp. §7) | M1 | Changing §2.2 / §2.5 / §7.1 requires re-sign-off |
| **Frozen evaluation tasks, baselines, metrics, anti-fudging rules** | `docs/evaluation-contract.md` | M1 + M6 | **Frozen but not executed** |
| **Implementation record + decision log D-1…D-3** | `docs/nfr2-nfr3.md` | M5 | Superseded where `nfr.md` is newer |
| **Iteration records** | `docs/sprint-1.md`, `docs/sprint-2-nfr-acceptance.md` | M1 | Point-in-time snapshots |
| **Research / related work** | `docs/research/` | M1 | Plan, not evidence |

---

## 3. One `analyze` run, end to end

```text
cli/main.py::_run_analyze
  ├─ validate repo path            → exit 2 if not a directory
  ├─ build ScoringConfig           → --mode / --preset / --exclude / --strict
  └─ AnalysisPipeline(clock).run(repo)
       │
       ├─ _guard("git")       GitHistory.collect_with_degradations
       │                        └─ commits_seen, git degradations (empty / shallow)
       ├─ _guard("metrics")   aggregate_file_metrics(now=clock.now())
       │                        └─ commits, churn, gini, age, recency decay
       ├─ _guard("scanner")   scan_repository(clock=)
       │                        └─ AST symbols, CC, nesting, imports, limitations
       │                        └─ per-file scanner degradations
       ├─ _guard("todo")      TodoDetector.detect(scan)
       │                        └─ TODO/FIXME/HACK/XXX counts, todo degradations
       ├─ _guard("scoring")   score_file × N  (4 base modes + optional composite)
       │                        └─ scores, breakdown, reasoning, severity, confidence
       ├─ rank_files / aggregate_folders / rank_folders
       ├─ tally degradations by (path, code)   ← deduplicated
       ├─ strict check → AnalysisDegradedError (exit 3)
       └─ AnalysisResult(stats=…, analyzed_at=clock.now().isoformat())
       │
  ├─ --report-coverage → stats.to_dict() as JSON
  ├─ --verbose         → stage timings + per-degradation hint (stderr)
  └─ renderer          → HTML (default) or JSON
```

Each `_guard` records `stage-failed` **and** the stage's elapsed time, so a failure never
disappears silently and the cost of each stage is always attributable
(`result.stats.stage_elapsed_ms`).

---

## 4. Extension points

| Want to add… | Touch | Do **not** touch |
|---|---|---|
| A new output format | implement `renderers.base.Renderer`, `@register("name")` | core pipeline |
| A new language for structure parsing | `scanner` suffix dispatch + a parser | `FileStructure` contract |
| A new scoring mode | `ScoringMode`, weights in `config/config.py`, signal map in `core/scoring.py` | existing modes' weight sums (they must stay 1.0) |
| A new reason code | `scanner.Limitation` (scan stage) **or** `DegradationCode` (other stages) **and** `REMEDIATION_HINTS` | — (the hint test will fail until you add one) |
| A new degradation source | a `_guard` stage in `pipeline.py` + a code | the accounting rule (dedup by path+code) |
| A new CLI subcommand | `cli/main.py` `build_parser` + a `_run_*` returning an exit code | the exit-code contract |

---

## 5. Where to look next

| Question | File |
|---|---|
| Why is this an NFR, and is it accepted? | [`docs/nfr.md`](nfr.md) |
| How do I build, test, submit? | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| What does the scanner promise? | [`scanner-interface.md`](scanner-interface.md) |
| What is the evaluation, and what is it *not*? | [`evaluation-contract.md`](evaluation-contract.md) |
| What was decided and when? | [`nfr2-nfr3.md`](nfr2-nfr3.md) |
