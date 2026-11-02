# Sprint 1: Requirements, Architecture, and Acceptance Record

Recorded: 2026-11-02 (Asia/Shanghai). The main-branch review baseline is [df67b8b](https://github.com/liuzhiyang5418/heatmap/commit/df67b8b5dfc2e845c8aea15fbbf69c709d267b71), including the scoring fix in [PR #14](https://github.com/liuzhiyang5418/heatmap/pull/14). This record accompanies a working branch; additions described here are not on main until the PR is merged. Meetings, boards, course submissions, and individual hours outside the repository have not been verified.

## Goal and scope

Sprint 1 aims to deliver a runnable analysis skeleton, user stories with acceptance criteria, architecture proposals for at least two non-functional requirements (NFRs), and a test foundation. For Python repository maintainers, the tool combines Git history with Python file structure to identify candidate hotspots and produce an inspectable report. A high score, a TODO candidate, or a mode named ROI is not proof of technical debt, a defect probability, or a financial return.

Member 1 owns requirements, sprint coordination, and documentation. Member 6 owns the dashboard, system tests, and evaluation. Work on other modules and approval of team decisions remain with the relevant members; this document does not replace team acceptance.

## User stories and status

Statuses distinguish the main baseline from this PR. Story points are proposed Fibonacci estimates for team discussion, not historical effort or completed points.

| ID | User story | Acceptance criteria | Priority / proposed points | Status and evidence |
|---|---|---|---|---|
| S1-01 | As a maintainer, I want to analyze a local Git repository and rank files so I can choose candidates for inspection. | The CLI selects a repository and mode; each file has a path, raw metrics, a score, and an explanation; analysis failures return an error. | P0 / 5 | The baseline has a [CLI](../src/githotmap/cli/main.py), [pipeline](../src/githotmap/core/pipeline.py), and HTML output. Two controlled repositories are covered by [system tests](../tests/test_sprint1_system.py). |
| S1-02 | As a maintainer, I want machine-readable output so I can review the report data. | The CLI writes JSON to a file or standard output, including metrics, mode, score breakdown, and status; empty results are parseable. | P0 / 2 | This PR adds a [JSON renderer](../src/githotmap/renderers/json.py) and [tests](../tests/test_json_renderer.py). Cross-version format stability and deterministic output are not yet guaranteed. |
| S1-03 | As a user, I want to start an analysis and inspect the result from a local web page. | The form accepts a local repository path and an existing mode, renders a report for valid input, presents readable errors, and binds only to loopback. | P0 / 3 | This PR adds an optional [Flask entry point](../src/githotmap/web/app.py) and [tests](../tests/test_web.py). Analysis is synchronous; background jobs, directory filtering, and online deployment are absent. |
| S1-04 | As a user, I want file identity and data status to remain clear after sorting. | Paths sort as text; LOC and contributor columns use their corresponding fields; cells link to rows by path; missing data is not shown as green; unusual paths display as text. | P0 / 3 | This PR updates the [HTML renderer](../src/githotmap/renderers/html.py) and adds a [browser test](../tests/test_html_browser.py). The current `missing` status covers both empty and missing files. |
| S1-05 | As a team member, I want requirements, risks, and acceptance criteria to be traceable. | Each story states ownership scope, priority, acceptance criteria, and evidence; open decisions and risks are recorded. | P0 / 3 | This is an M1 draft; corresponding issues and team confirmation have not been verified. |
| S1-06 | As a team member, I want regression checks to run after changes. | Unit, system, and browser checks can run; a PR workflow runs tests and reports failures. | P0 / 3 | This PR adds [.github/workflows/tests.yml](../.github/workflows/tests.yml). Test evidence and its limits are recorded below. |
| S1-07 | As a maintainer, I want to rank Python files with the proposal's C×R baseline and export the top 20. | The team agrees the formula, complexity definition, normalization, and frozen baseline; fixed inputs are checked for raw values, breakdown, and ranking. | P0 / 5 | **Incomplete; coordination with M2, M4, and M5 is needed.** The current `complexity` mode combines weighted signals and is not the proposed C×R formula. This PR does not change scoring. |

## NFR architecture proposals

The supplied requirements identify performance, robustness and auditability, and reproducibility as candidates. The latter two are elaborated below. Adoption and thresholds require team agreement, and none has passed complete acceptance.

### NFR-2: Robustness and auditability

- Scenario and candidate measures: test each of 12 agreed fault or boundary classes; default mode should not crash and should expose degradation or skip reasons; strict mode should return a nonzero exit code for agreed degradations. Freeze the actual classes, denominator, and platforms before testing.
- Alternative A: fail immediately on an exception. This is simpler but cannot return results for other analyzable files.
- Proposed B: return best-effort results by default and propagate machine-readable reason codes and coverage counts from scanner, TODO, and Git modules through `AnalysisResult` to HTML/JSON; offer a separate strict mode. This requires M2–M6 to agree status and error semantics.
- Current gap: scanner has `limitations` and `ScanStats`, but the [pipeline](../src/githotmap/core/pipeline.py) can silently fall back on scanner or TODO exceptions. This PR displays existing `status` and `confidence`; coverage and reason propagation remain incomplete. `size_bytes == 0` does not distinguish an empty file from missing data.
- Proposed acceptance: assert exit behavior, reason codes, counts, and HTML/JSON consistency for each class, and retain failing samples. This has not been executed.

### NFR-3: Reproducibility and verifiability

- Scenario and candidate measures: after fixing the repository commit, worktree, parameters, scoring configuration, clock, tool version, and platform, two normalized outputs should match; compare Windows and Linux under an agreed contract and record the format version and baseline hash.
- Alternative A: remove only the analysis timestamp before comparison. This is a small change, but metrics can depend on the current time, so it is insufficient by itself.
- Proposed B: inject a fixed analysis clock; freeze inputs and configuration; define sorting, path, and serialization rules; and retain versions, baselines, and expected hashes. Core-module changes and a baseline change log are required.
- Current gap: results contain `analyzed_at` and some metrics depend on the current time. There is no deterministic serialization contract, cross-platform experiment, or frozen hash. JSON export in this PR is not reproducibility acceptance evidence.
- Proposed acceptance: run each of at least three frozen repository snapshots twice, compare normalized outputs and hashes, then validate in cross-platform CI. This has not been executed.

### NFR-1: Performance and scale (candidate)

The supplied requirements propose targets including 3,000 files within five seconds. These have not been remeasured on the current baseline with fixed data and hardware. First freeze repository size, commit history, hardware, repetition count, and memory measurement method; then compare cold and warm runs. M4 and M5 should participate in optimization and target decisions.

## Tests and evidence

- Local baseline: a separate test repository was built from a main-file snapshot, with an additional empty commit to satisfy an existing two-commit test assumption; 149 existing tests passed. This constructed history is not the original GitHub history.
- Sprint 1 changes at `9516f15`: macOS / Python 3.11 produced **161 passed and 1 skipped**, including CLI-to-JSON/HTML tests using two synthetic Git repositories, a Flask test client exercising the real pipeline, and Node-based DOM simulation for sorting and linking. Synthetic data does not replace real-project validation; a simulated DOM does not replace a real browser.
- Local headless Chrome could not start, so the local browser test was skipped. It requires `HEATMAP_CHROME` and permission to launch a headless browser. On GitHub Actions, the [push run](https://github.com/liuzhiyang5418/heatmap/actions/runs/41438335271) for `9516f15` passed on Linux with Python 3.10, 3.11, and 3.12, including the Chrome interaction test. Check the current PR checks for subsequent commits.
- The [research evaluation plan](research/evaluation-plan.md) remains a plan. There are no participant results or conclusions establishing performance, NFR compliance, or scoring accuracy.

## Risks and open decisions

| Item | Impact | Next step / relevant members |
|---|---|---|
| The proposal calls for C×R, a frozen baseline, and a churnmap extension; the repository uses weighted scoring modes. | Full acceptance of the proposed ranking and algorithm reproduction cannot be claimed. | M1 coordinates a scope decision; M2/M4/M5 review metrics and formula and record the decision. |
| Scanner and TODO failures can silently degrade; empty files and missing data share a status. | Users may mistake an unanalyzable file for a low-risk file. | M2/M3/M5 provide reasons and statuses; M6 displays and tests them. |
| Synchronous Flask analysis may take a long time for a large repository. | The interface may appear unresponsive. | M6 measures the behavior before deciding on progress feedback or background work; no performance guarantee is claimed. |
| Real-repository validation, user studies, and cross-platform checks are missing. | There is insufficient evidence for the sprint exit criteria. | M1/M6 and the team select two fixed real-repository versions and reviewers, then record commands, results, and issues. |
| Meetings, a burndown chart, contribution records, and formal acceptance are not evidenced in the repository. | Historical progress cannot be reconstructed reliably from this snapshot. | M1 collects existing records and records missing information prospectively rather than inventing it. |

**Exit status: partially complete.** Team review, real-repository demonstrations, a scoring-scope decision, and sprint acceptance remain outstanding. Passing code checks does not by itself constitute team acceptance.
