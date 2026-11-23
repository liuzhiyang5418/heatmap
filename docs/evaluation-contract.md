# Evaluation contract — frozen

| Item | Content |
|------|---------|
| Contract version | **v1.0**, frozen 2026-11-20 (Sprint 2 close) |
| Status | **Frozen, NOT executed.** No participant data has been collected. |
| Applies to | Final report evaluation chapter and the Sprint 3 demo |
| Related | `docs/research/evaluation-plan.md` (method), `docs/research/literature-review.md` (sources P1–P6) |

The course asks teams to **freeze** tasks, data, baselines, metrics, thresholds and test cases
*before* comparing anything, so that a disappointing result cannot be explained away by moving
the target. This document is that freeze. Changing anything here after data collection starts
requires a new version number and a written reason.

---

## 1. Three separate questions (do not merge them)

| ID | Question | What answers it | Status |
|----|----------|-----------------|--------|
| Q1 | **Data correctness** — does the tool compute what it claims for known inputs? | automated tests | ✅ covered by the suite |
| Q2 | **Candidate relevance** — is the ranking a meaningful worklist? | manual review of high-score files and counter-examples | ❌ not executed |
| Q3 | **Interface effect** — does the file map help a reader decide? | controlled task study | ❌ not executed |

Explicit non-claim: *a participant correctly finding the top-3 files proves they read the
tool's ordering, not that the ordering reflects real technical debt.*

---

## 2. Q1 — Frozen correctness cases

These are frozen as the "known-answer" set and are asserted in code, so the contract cannot
drift without a failing test.

| # | Input | Frozen expectation | Test |
|---|-------|--------------------|------|
| C1 | repository with a non-ASCII filename | that file appears with its real path, `commits > 0`, `score > 0` | `tests/test_scanner_codes.py`, `tests/test_git.py` |
| C2 | repository with a syntax-error / binary / oversized file | each gets the matching reason code and is counted once | `tests/test_scanner_codes.py`, `tests/test_nfr2_system.py` |
| C3 | fixed metrics, four modes | score in `[0, 100]`, `sum(breakdown) == 100` | `tests/test_scoring.py` |
| C4 | same repository, two runs, fixed clock | `canonical()` byte-identical | `tests/test_determinism.py` |
| C5 | three frozen snapshots | digest stable across re-runs and independent of checkout path | `tests/test_frozen_fingerprints.py` |
| C6 | degraded file outside `--limit` | `--strict` still exits 3 | `tests/test_pipeline_degradation.py` |

Fixed parameters for C3–C5: default `ScoringConfig`, default caps, `limit` as stated per case,
fixed clock, LF line endings.

---

## 3. Q2/Q3 — Frozen human-evaluation tasks

Four tasks, reused verbatim across conditions. Ground truth is computed **from the frozen data
snapshot before any session**, never after seeing results.

| ID | Task | Ground truth / scoring | Metric |
|----|------|------------------------|--------|
| T1 | Find the three highest-scoring files | computed from the same snapshot; 1 point per correct file; ties resolved by path | 0–3 points, completion, time |
| T2 | Find the top-level directory with the highest ratio of high-score files | high-score files ÷ analysable files; **high score = ≥ the dataset's 75th percentile**; minimum directory size and tie rule frozen in the answer key | 1 point directory + 1 point ratio, time |
| T3 | Explain why a named file needs review | must cite **two real metrics** and must note candidate ≠ confirmed | 1 point per item, 0–3 |
| T4 | Identify files with missing data | answer key built from the `status` field; missing ≠ low risk | correctness, time |

`--limit` is fixed per snapshot so the answer key is unambiguous.

**Why T2 uses a percentile rather than `severity ≥ high`.** The first implementation defined
"high score" as `critical`/`high`, which depends on absolute thresholds (75/50). On a small
repository the top file may score 25, so *no* file qualifies and T2 becomes unanswerable —
observed on this very repo (`roi` mode, maximum 24.99). The 75th percentile adapts to each
dataset, stays reproducible, and the actual threshold is written into the answer key so the
ground truth is frozen alongside it. This is a pre-execution refinement of the task definition,
not a post-hoc change: it was made before any session, and `docs/nfr.md` §7 records that
changing T2's rule after data collection requires a new contract version.

---

## 4. Conditions (fair baseline)

| Arm | Interface | Held constant |
|-----|-----------|---------------|
| **A** | searchable, sortable table + evidence detail | same snapshot, same metrics, same filters, same fields, same loading state |
| **B** | identical table + detail **plus** the file map | as above |

The only manipulated variable is the presence of the map. Directory views, extra evidence
fields or different default sorting are **not** part of either arm; if introduced later they
must be added to *both* arms before the contract is used.

---

## 5. Metrics and decision rules

| Metric | Definition | Reported as |
|--------|------------|-------------|
| Completion rate | tasks finished within the time limit | proportion, including failures |
| Task score | per §3 answer key | mean, distribution, paired difference |
| Time on task | wall clock to submission | median + spread |
| Failure handling | timeouts and device failures | counted, not silently dropped |

Per-task reporting; each participant is one unit (multiple tasks are **not** independent
observations). Small samples are reported descriptively; if inference is needed, the test is
chosen from the actual design and effect size + uncertainty are reported.

---

## 6. Participants and procedure (frozen)

1. Pilot with 2 people to check instructions, difficulty and time limit.
2. Recruit **8–12** participants (target, not a guaranteed sample).
3. Two task datasets **X** and **Y**; balance order and data with A-X→B-Y, B-X→A-Y, A-Y→B-X,
   B-Y→A-X.
4. Equal training plus an independent practice task per arm.
5. Record the time limit, allowed actions, timeout rule and device-failure rule **before**
   the first session.

---

## 7. Reporting rules (frozen anti-fudging clauses)

- Report failures and timeouts, not only successful sessions.
- Do not delete a task because the map performed poorly on it after seeing results.
- T3 is graded against the pre-written answer key, blind where possible.
- Do not interpret a Q3 result as evidence about Q2, or a Q2 result as evidence about accuracy
  of the score.
- Convenience sampling, learning effects, data scale and scenario limits must be disclosed.

---

## 8. Non-goals

- The score is **not** proven equal to technical debt, defect probability, repair hours or
  financial return.
- `complexity` is **not** AST cyclomatic complexity; `roi` is **not** measured return on
  investment.
- No performance claim: the deferral is recorded in `docs/nfr.md` §5.
- The study does **not** reproduce P4's reported +24 % correctness / −12 % time; that figure
  comes from a differently designed, untrained task and must not be quoted as our result.

---

## 9. Data minimisation

Store only: anonymous participant id, required experience band, arm/dataset assignment, task
answers, scores, timings and failure reason. Public reporting uses synthetic or already-public
repositories; no private paths, personal emails, non-public source or identifying browser data
are committed to the repository.

---

## 10. Execution status (honest record)

| Stage | State |
|-------|-------|
| Contract frozen (this file) | ✅ 2026-11-20 |
| Answer keys computed from snapshots | ❌ to do at execution time |
| Pilot (2 people) | ❌ not run |
| Main sessions (8–12) | ❌ not run |
| Q1 automated correctness | ✅ covered by the test suite |

**Nothing in this document may be reported as a result until §10 shows execution.** The
research documents remain a plan; they are not evidence of performance, NFR compliance or
scoring accuracy.
