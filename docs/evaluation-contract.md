# Evaluation contract — frozen

| Item | Content |
|------|---------|
| Contract version | **v1.1**, amended 2026-11-23; v1.0 frozen 2026-11-20 (Sprint 2 close) |
| Status | **Partly executed.** Q2 answered by historical replay (§11); Q3 (participant study) **dropped, not executed**. No participant data was ever collected. |
| Applies to | Final report evaluation chapter and the Sprint 3 demo |
| Related | `docs/research/evaluation-plan.md` (method), `docs/research/literature-review.md` (sources P1–P6), `docs/evaluation-replay-result.md` (Q2 measured result) |

The course asks teams to **freeze** tasks, data, baselines, metrics, thresholds and test cases
*before* comparing anything, so that a disappointing result cannot be explained away by moving
the target. This document is that freeze. Changing anything here after data collection starts
requires a new version number and a written reason.

---

## 1. Three separate questions (do not merge them)

| ID | Question | What answers it | Status |
|----|----------|-----------------|--------|
| Q1 | **Data correctness** — does the tool compute what it claims for known inputs? | automated tests | ✅ covered by the suite |
| Q2 | **Candidate relevance** — is the ranking a meaningful worklist? | **historical replay** against real commit windows (§11) | ⚠️ executed, weak-to-moderate — see result doc |
| Q3 | **Interface effect** — does the file map help a reader decide? | controlled task study | ❌ dropped, not executed (§11) |

Explicit non-claim: *a participant correctly finding the top-3 files proves they read the
tool's ordering, not that the ordering reflects real technical debt.*

**v1.1 status note.** Q2 no longer depends on human review: the historical-replay method
(§11) scores a repository at commit *t0*, then measures how much the flagged files actually
churned in a later window. Q3 has no substitute — its interface question is reported as
**not answered**, never as answered by proxy.

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

## 3. Q3 — Frozen human-evaluation tasks (frozen, **NOT EXECUTED**)

> **v1.1:** these tasks were defined for the participant study that v1.1 drops. They are kept
> verbatim because a later team may revive Q3; until then they must not be described as
> executed. T1/T2/T4 are *interface* tasks — a person reads the UI — so none of them can be
> answered by the replay method in §11.

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

## 6. Participants and procedure (frozen, **NOT EXECUTED**)

> **v1.1:** no session of any kind was run. Nothing below happened; it is retained as the
> alternative method if a future cohort restores Q3.

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
| Contract frozen v1.0 | ✅ 2026-11-20 |
| Contract amended v1.1 (Q3 dropped, Q2 → historical replay) | ✅ 2026-11-23 |
| Q1 automated correctness | ✅ covered by the test suite |
| Q2 historical replay | ✅ executed 2026-11-23 — `docs/evaluation-replay-result.md` |
| Answer keys T1–T4 computed | ❌ not computed (they belong to the dropped Q3) |
| Pilot (2 people) | ❌ not run — **dropped** |
| Main sessions (8–12) | ❌ not run — **dropped** |

**Reporting rule.** A question may be reported as *answered* only if the row above shows ✅.
Q3's row can never show ✅ now, so the report must state that the interface question is
**open** — the tool's visual design is motivated by the literature and the Sprint 3
walkthrough, not by our own measured effect. Q2 may be reported, but only with the sample-size
guard and caveats that §11 and the result doc attach to it.

---

## 11. Q2 method — historical replay (v1.1, frozen)

**Why this replaced human review.** Q2 asks whether the ranking is a useful worklist. That can
be tested against reality instead of opinion: score the repository at commit *t0*, then look at
what the next window of commits actually touched. No participants, no annotation bias, and the
result is reproducible by anyone with the repository. The cost is that it measures *predictive
overlap*, not *usefulness to a developer* — those are different claims and §11.4 keeps them
apart.

### 11.1 Procedure (frozen)

1. Resolve `t0 = --from`, `t1 = --to`; require `t0` to be a strict ancestor of `t1`.
2. Materialise a detached worktree at `t0` and run the normal analyzer on it (`--mode roi`),
   producing `scores[path]` exactly as a user would see at that moment.
3. From `t0..t1`, sum per-file churn as `added + deleted` over `git diff --numstat --no-renames`.
4. `comparable = {path : path ∈ scores ∧ path changed in window}`. Files that did not exist at
   `t0` (new files) cannot be scored and files deleted in the window are listed separately;
   neither enters `comparable`.
5. Compare `tool_top_k` (top-K by `scores`) with `actual_top_k` (top-K of `comparable` by churn).

### 11.2 Metrics (fixed definitions)

| Metric | Definition | Role |
|--------|------------|------|
| Precision@K | `|tool_top_k ∩ comparable| / K` | of K flagged files, how many were actually touched |
| Random baseline | `|comparable| / |scores|` | expected Precision@K for a blind pick |
| **Lift** | `Precision@K / random baseline` | **primary metric** — the only one that removes the "almost everything churned" effect |
| Recall@K | `|tool_top_k ∩ actual_top_k| / K` | did the flag set contain the K heaviest files |
| Spearman ρ | rank correlation of `scores` vs churn **within `comparable`** | monotonicity; a guard against "right set, wrong order" |

**Lift is primary, Precision is not.** When a window touches most of the repository the
baseline approaches 1 and Precision approaches 1 for *any* ranking; quoting Precision alone
would flatter the tool. Conversely a narrow window makes Precision collapse for a good tool
(§11.4). Lift normalises for both.

### 11.3 Sample-size guard (frozen)

- `comparable < 2·K` → the run emits a `warnings` entry and the result **must not be stated as
  a conclusion**, only as a direction.
- `comparable < K` → additional warning: Precision@K cannot exceed `comparable/K`, so a low
  value does not by itself show bad ordering.
- `comparable = 0` → the run aborts.

### 11.4 Window selection (frozen, to prevent cherry-picking)

- **Primary window:** the span from the **Sprint 1 final tag** (`daf9500`, tagged
  `sprint1-final`, 2026-11-07) to `HEAD`. Fixed here **before** any result is reported.
- **Sensitivity window:** the shortest recent window actually available (`HEAD~8..HEAD`). Its
  purpose is to expose the method's failure mode, **not** to be discarded if it looks worse.
- Any additional window must be justified by a rule stated in advance (e.g. "each past sprint"),
  never by its result. A window that performs badly is reported, not hidden.
- Changing this rule after a result exists requires contract version v1.2.

### 11.5 What this method must never claim

- Not causal: overlap shows the flag set *contained* files that later churned; it does not show
  the churn happened *because* those files were flagged, nor that acting on the list is
  beneficial.
- Not Q3: it says nothing about whether a *person* reads the map faster or decides better.
- Not long-term: a window of weeks cannot speak to the repository's lifetime trend.
- Not accuracy of the score itself: the score is a candidate ranking, not a defect detector.
