# Non-Functional Requirements — frozen scope

| Item | Content |
|------|---------|
| Iteration | Sprint 2 (weeks 6–9), closed at `main` @ `e1f2917` |
| Team size | 6 — the course requires **at least 2** NFRs with an architecture rationale |
| Selected | **NFR-2 Robustness & auditability**, **NFR-3 Reproducibility & verifiability** |
| Status | Implementation and automated acceptance in place; §7 lists what still needs team sign-off |

This document replaces the "candidate" list in `docs/scanner-interface.md` §8 and closes
pending item #4 there ("which NFRs are finally counted"). It states what is measured, which
architecture decision each requirement forced, and why the remaining candidates were dropped.

---

## 1. Why these two

The tool turns Git history into a **ranked worklist** that a team uses to schedule refactoring.
That use decides the choice:

- **NFR-2** — a ranking that is silently wrong is worse than no ranking, because the team
  will act on it. Sprint 1 review produced a concrete instance: non-ASCII paths made history
  metrics collapse to `0` with no error (M4-2). Robustness alone (don't crash) would not have
  caught it; auditability (every degradation carries a machine-readable reason) does.
- **NFR-3** — the course requires a **frozen evaluation contract**. Without a deterministic
  result pipeline, no "before vs after" or "our tool vs hotspot" comparison is meaningful:
  differences could be clock drift rather than code change.

They are also orthogonal: NFR-2 governs *what happens when input is bad*, NFR-3 governs
*whether two runs are comparable*.

---

## 2. NFR-2 — Robustness and auditability

### 2.1 Statement

> Given arbitrary input (bad encoding, binary files, oversized files, non-ASCII paths,
> shallow clones, unreadable files, empty repositories, non-Git directories, corrupt
> objects), the tool must **not crash** and must **not degrade silently**: every skipped or
> limited file carries a machine-readable reason code that reaches the result and the report.

### 2.2 Measurable acceptance

| ID | Metric | Target | Evidence |
|----|--------|--------|----------|
| NFR-2.1 | Fault classes that crash the pipeline | **0** | `tests/test_robustness.py` (#1–6,8–12), `tests/test_git_robustness.py` (#9,12), `tests/test_todo_robustness.py` (#2–6,10), `tests/test_analysis_robustness.py` |
| NFR-2.2 | Degraded files carrying a reason code | **100%** | `tests/test_scanner_codes.py`, `tests/test_diagnostics_consistency.py` |
| NFR-2.3 | Coverage visible to a reader | `files_matched` / `files_emitted` / `files_degraded` + per-code counts rendered in HTML and JSON | `tests/test_html.py`, `tests/test_nfr2_system.py`, `tests/html_interactions.js` |
| NFR-2.4 | `--strict` exit code when any degradation exists | **3** (also when the degraded file falls outside `--limit`) | `tests/test_pipeline_degradation.py`, `tests/test_nfr2_system.py` |
| NFR-2.5 | Blind `except` in business code | **0** (ruff `BLE001` / `S110`) | `ruff check src tests` → clean |

Fault-class coverage (the 12 in the Sprint 2 plan): non-ASCII path, binary, oversized
(>2 MB), syntax error, declared alternate encoding, symlink, empty repo, non-Git directory,
shallow clone, unreadable file, deep nesting, corrupt Git object.

### 2.3 Architecture decisions

| # | Decision | Alternative rejected |
|---|----------|----------------------|
| D1 | **One reason-code source.** `scanner.Limitation` is authoritative; `core.diagnostics.DegradationCode` references its values instead of copying literals. | Two independently maintained enumerations — this is exactly how M4-2 stayed invisible. |
| D2 | **Dual policy.** Default = best-effort with recorded degradations; `--strict` = any degradation aborts with exit 3. | Always fail-fast (loses the other files' results); always degrade (a CI can pass on a repo it never analysed). |
| D3 | **Stage guards.** Each stage runs inside a guard that records `stage-failed` plus elapsed time; no bare `except: pass` anywhere. | Silently skipping a failed stage — the Sprint 1 implementation did this twice. |
| D4 | **Degradation accounting is deduplicated by `(path, code)`.** | Counting events: scanner *and* TODO both flag the same `not-text` file, doubling the coverage figure. |

Dependency direction is fixed at `core → scanner`; `scanner` never imports upward, so the
shared code module cannot reintroduce the `config ⇄ core` cycle.

### 2.4 Known limits

- Passing fault tests is **evidence for the tested classes**, not a proof of zero crashes for
  arbitrary repositories.
- File-permission behaviour differs under elevated accounts; unreadability is exercised via
  injected I/O failure rather than a real chmod.
- Symlink scenarios skip on hosts that cannot create links (recorded as skips, not passes).

---

## 3. NFR-3 — Reproducibility and verifiability

### 3.1 Statement

> For a fixed repository, fixed parameters and fixed version, two runs produce the **same
> result** apart from explicitly declared non-deterministic fields; a stable digest identifies
> that result so regressions can be detected.

### 3.2 Measurable acceptance

| ID | Metric | Target | Evidence |
|----|--------|--------|----------|
| NFR-3.1 | Two runs of `canonical()` | **byte-identical** | `tests/test_determinism.py` |
| NFR-3.2 | Frozen snapshots with stable digests | **3 snapshots**, digest stable across re-runs | `tests/test_frozen_fingerprints.py` |
| NFR-3.3 | Cross-platform behaviour | same contract on ubuntu + windows, Python 3.10–3.12 | `.github/workflows/tests.yml` matrix |
| NFR-3.4 | Format traceability | `AnalysisResult.schema_version` present; bump on format change | `tests/test_determinism.py` |
| NFR-3.5 | Time sources outside the clock module | **0** (`datetime.now` / `perf_counter` / `time.time`) | `tests/test_clock.py::test_time_sources_are_confined_to_clock_module` |

### 3.3 Architecture decisions

| # | Decision | Alternative rejected |
|---|----------|----------------------|
| D1 | **A single injectable clock** live at `githotmap/clock.py` (top level, not `core/`), so both `core` and `scanner` can use it without a cycle. `FixedClock` freezes `now()` and zeroes elapsed time. | Patching `datetime` in tests (brittle); putting the clock in `core/` (`scanner` would import `core`, re-creating a cycle). |
| D2 | **`canonical()`** drops clock fields and host identity (`analyzed_at`, `scanned_at`, `elapsed_ms`, `stage_elapsed_ms`, `repo_path`, `repo_urn`), sorts keys recursively, rounds floats to 6 dp, normalizes path separators, rejects NaN/inf. | Comparing `to_dict()` directly — timestamps and checkout paths always differ. |
| D3 | **`fingerprint()`** = lowercase SHA-256 of the canonical UTF-8 bytes. | Hashing `repr()` — unstable across Python versions. |
| D4 | **Frozen synthetic snapshots** with fixed `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`, LF-locked `.gitattributes`, and an injected fixed clock. | Committing expected digests produced on one OS — working-tree normalization makes raw digests legitimately differ across platforms. |

### 3.4 Known limits

- The digest is a **regression identifier within a normalized environment**; the accepted
  contract is "double-run self-consistency + checkout-path independence", not "identical raw
  digest on every OS". This deviation from the original plan is recorded as D-3 in
  `docs/nfr2-nfr3.md`.
- Snapshots are synthetic; they do not establish equivalence for arbitrary real repositories
  or every Git/Python version.

---

## 4. Excluded NFRs and why

Recording the exclusions is part of the requirement exercise: it shows the scope was bounded
deliberately rather than by omission.

| Candidate | Why not adopted |
|-----------|-----------------|
| Security | Local read-only CLI: no network listener, no credentials, no multi-tenant surface. Hardening it would defend an attack surface that does not exist. |
| Availability / service capacity | Not a deployed service; there is no SLA object. |
| Internationalisation | Audience is developers running it locally; the report UI is English and adequate. Cost/benefit is poor at this scale. |
| Compliance / privacy | Folded into NFR-2's data minimisation (no participant data, no personal paths in stable diagnostic detail). Too thin to stand alone. |
| **Performance (candidate NFR-1)** | Real and measured, but **out of scope** — see §5. The course requires ≥2 NFRs and two are delivered; optimising `git` collection would rewrite the same module that NFR-3 just stabilised, and would invalidate the frozen fingerprints. |

---

## 5. Out of scope: performance and scale (candidate NFR-1)

> **Scope decision:** NFR-1 is **not** delivered. The course requires at least two NFRs for a
> 6-person team and NFR-2 + NFR-3 satisfy that. Sprint 3 does not add performance work; it adds
> automated tests, debugging and maintenance support. What remains below is a *measured
> baseline kept as future work*, not a delivery commitment.
>
> Clarification: **no performance optimisation** does not mean **no performance guard** —
> Sprint 3 adds a regression assertion so the current behaviour cannot silently degrade.

A baseline was measured during Sprint 2 planning so the numbers are not invented later:

| Repository | Files | `analyze` wall time |
|---|---|---|
| this repo | 54 | 2.23 s (git collection 1.97 s ≈ 88%) |
| synthetic | 300 | 1.41 s |
| synthetic | 1000 | 4.51 s |
| synthetic | 3000 | 14.71 s |
| large-history (300 × 30 commits) | 300 | 2.15 s (GitPython collect 1.72 s) |

Memory: 15.8 MB peak for 1000 files (≈16 KB/file).

The dominant lever is already identified: `git log --numstat` single pass costs 0.264 s on the
large-history fixture versus **1.723 s** for per-commit GitPython stats (6.5×). It is recorded
here as the first step for any future performance work, but it is **not scheduled**: it rewrites
the module that NFR-3 just stabilised and would invalidate the frozen fingerprints.

---

## 6. Traceability

| Requirement | Implementation | Acceptance |
|---|---|---|
| Single reason-code source | `scanner/models.py` (`Limitation`, `LIMITATION_CODES`), `core/diagnostics.py` (`DegradationCode`) | `tests/test_scanner_codes.py`, `tests/test_diagnostics_consistency.py` |
| Degradation propagation | `core/pipeline.py` (`_guard`, per-stage stats) | `tests/test_diagnostics.py`, `tests/test_pipeline_degradation.py` |
| Strict mode | `config.degrade_policy`, `cli --strict`, `AnalysisDegradedError` | `tests/test_pipeline_degradation.py`, `tests/test_nfr2_system.py` |
| Coverage reporting | `renderers/html.py` panel, `AnalysisStats.to_dict()` | `tests/test_html.py`, `tests/html_interactions.js` |
| Injectable clock | `githotmap/clock.py`, `AnalysisPipeline(clock=)`, `scan_repository(clock=)` | `tests/test_clock.py` |
| Canonical output & digest | `core/models.py` (`canonical()`, `fingerprint()`, `schema_version`) | `tests/test_determinism.py` |
| Frozen snapshots | `tests/test_frozen_fingerprints.py` | same |
| Quality gate | `.github/workflows/tests.yml` (whole-repo ruff + mypy) | CI status checks |

## 7. Open decisions (team sign-off required)

1. **Fault-class list** — the 12 classes above are implemented; confirm they are the agreed denominator.
2. **Strict-mode semantics** — should every warning be fatal, or only agreed degradation classes?
3. **Cross-platform equivalence boundary** — accept the D-3 contract (self-consistency + path independence) as the acceptance criterion, or require identical raw digests on both OSes.

Until these are signed off, this document records **implemented and tested behaviour**, not team acceptance.
