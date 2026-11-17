# Sprint 2 NFR Acceptance and Presentation Evidence

Snapshot: 17 November 2026 (Asia/Shanghai). The reviewed main commit is
[`ea6a47b`](https://github.com/liuzhiyang5418/heatmap/commit/ea6a47bc0f62fbfc41d2109f522928d266e41de3).
The requested deadline is Friday, 20 November. The target NFRs are robustness
and auditability (NFR-2) and reproducibility (NFR-3), as confirmed by the
responsible team member on 17 November.

## Current status

| Work | Status | Evidence and next step |
|---|---|---|
| NFR-2 diagnostic model and scanner code alignment | **On main** | [PR #18](https://github.com/liuzhiyang5418/heatmap/pull/18) and the [scanner integration commit](https://github.com/liuzhiyang5418/heatmap/commit/ea6a47bc0f62fbfc41d2109f522928d266e41de3) define the shared codes and statistics. |
| NFR-2 stage guards and strict mode | **On main; integration incomplete** | [PR #19](https://github.com/liuzhiyang5418/heatmap/pull/19) added stage guards; [PR #20](https://github.com/liuzhiyang5418/heatmap/pull/20) corrected file counts and strict checks before the display limit. TODO and Git producer diagnostics still need integration. |
| TODO and Git producer diagnostics | **Open PRs** | [M3 PR #16](https://github.com/liuzhiyang5418/heatmap/pull/16) and [M4 PR #17](https://github.com/liuzhiyang5418/heatmap/pull/17) are open. After review, M5 needs to map their diagnostic records into the pipeline; rerun end-to-end checks. |
| NFR-2 report panel and system checks | **This local branch** | The panel displays counts, reason-code totals and stage events, and marks limited data in gray. [System checks](../tests/test_nfr2_system.py) exercise actual fault fixtures and strict-mode behavior. Review and CI are pending. |
| NFR-3 fixed clock | **Separate branch** | [`b2408df`](https://github.com/liuzhiyang5418/heatmap/commit/b2408df808347cfdd75cc743d6b6359e6147b203) is one commit ahead of the reviewed main and has no PR at this snapshot. Its 14 clock tests passed locally. Coordinate its review and integration. |
| NFR-3 canonical output and cross-platform fingerprints | **Open** | Agree the canonical fields, portable repository identity, ordering and hash format; freeze fixtures and run them on Linux and Windows. No cross-platform acceptance result is recorded. |
| CI and code quality | **Partial** | [Main CI](https://github.com/liuzhiyang5418/heatmap/actions/runs/43467734797) passed for Python 3.10–3.12 on Ubuntu, including its browser checks. This local branch adds a scoped report-quality job; GitHub has not run it yet. Repository-wide Ruff and Mypy checks still report existing findings. |

Main provides a versioned JSON data model. Canonical serialization and portable
fingerprints remain open. Heatmap scores support candidate selection for review.

## Ownership and handoffs

| Owner | Responsibility |
|---|---|
| M1 | Requirements, acceptance criteria, sprint tracking, dependency coordination, and evidence records. |
| M6 | Dashboard, report presentation, system/fault-injection tests, test CI, and evaluation fixtures and results. |
| M2 | Scanner behavior, file discovery and decoding, and scanner reason-code production. |
| M3 | TODO detection and its read/tokenization diagnostics. |
| M4 | Git history collection and empty/shallow-repository diagnostics. |
| M5 | Pipeline integration, scoring, strict-mode implementation, and the product canonical-output/fingerprint contract. |

The M1/M6 patch changes the report renderer, tests, test workflow, and this
record. It contains no scanner, TODO, Git, scoring, or pipeline implementation
changes. The fixed-clock implementation remains with its existing branch owner.
M6 reproduces defects and supplies test cases; each module owner implements the
corresponding repair. M1 coordinates and records those handoffs.

## Member 1 / Member 6 deliverables

1. **Coverage panel (M6):** submit the HTML renderer and browser checks in this
   branch. Show matched, scored, listed, and limited-file counts, aggregate reason
   codes, and available stage events. The limited-file count is before the
   display limit; file paths cover the displayed selection.
2. **Fault checks (M6):** submit `tests/test_nfr2_system.py` and the panel
   interaction tests. Complete the outstanding scenarios in the matrix after the
   producer PRs and diagnostic semantics are agreed. Keep skipped cases and
   operating-system prerequisites visible in the test report.
3. **Quality gate (M6):** review the scoped `nfr-report-quality` CI job. It runs
   Ruff on the report and its Python checks and Mypy on the report renderer with
   imported modules silenced. Expand the gate only after the team addresses the
   existing whole-repository findings.
4. **Acceptance and coordination (M1):** record the scenario list and obtain
   module-owner agreement on expected reason codes; track PR #16/#17 and the clock
   branch, and record the owner and evidence for each open item.
5. **Reproducibility evaluation (M6):** prepare three candidate test fixtures,
   configurations, expected outputs and evaluation hashes. M5 defines and
   approves the product canonical-output contract. Update the candidate
   baselines to that contract, then run Linux/Windows comparisons and retain
   the evidence. The local projection and hashes are evaluation proposals.
6. **Presentation inputs (M1/M6):** retain the status table, verified test
   outputs, a synthetic report screenshot, the open gaps, and final CI links.
   State whether each item is on main, on a team branch, or pending review.

## Proposed NFR-2 fault matrix

This acceptance proposal contains 12 scenario classes. For each applicable
class, check default and strict behavior, reason codes, counts, and the report.
The team should freeze expected outcomes and platform exceptions before the
final acceptance run.

| Scenario | Evidence at this snapshot |
|---|---|
| Binary data in a Python file | Local system check passes for `not-text` and strict rejection. |
| File larger than the scanner limit | Local system check passes for `too-large` and strict rejection. |
| Python syntax error | Local system check passes for `syntax-error` and strict rejection. |
| Invalid source encoding | **Gap:** in a controlled UTF-8 fixture containing an invalid byte in a comment, the result recorded no limitation or reason code. Agree detection and reporting with M2/M3/M5. |
| Tracked symbolic link | Local macOS check passes for `symlink` and strict rejection; platforms without link permission need an explicit skip. |
| File read permission failure | Local system check passes using an injected `PermissionError`; exercise actual OS permissions separately. |
| Non-ASCII filename | Local system check preserves the path through Git and scanner. |
| Empty Git repository | A local empty-repository fixture records generic `stage-failed`; the specific `empty-repo` diagnostic is part of open PR #17 and requires integration. |
| Shallow Git history | Open PR #17 adds a real shallow-clone fixture; pipeline propagation remains open. |
| Tracked file removed from the worktree | **Gap:** a local fixture produced `status=missing` with no limitation or reason code, and strict mode returned a result. Agree and implement the file-level reason and strict behavior. |
| Directory that is not a Git repository | Main's `test_pipeline_degradation.py` checks recorded stage failure and strict rejection. |
| Scanner or TODO stage raises | Local system checks inject both failures, verify their stage codes, and verify strict rejection. |

M3's open PR contains additional module-level fault fixtures. Reuse them after
integration and add cases for unavailable directories, mixed faults, and
platform-specific behavior where the agreed contract requires them.

## Reproducibility acceptance contract

Before collecting final evidence, record: repository snapshot and worktree,
tool and dependency versions, parameters, fixed analysis time, schema version,
operating system, sorting and tie rules, portable path/identity rules, and the
canonical representation used for the fingerprint. Do not compare hashes from
different contracts.

The clock branch passed 14 tests locally. Three frozen fixtures now cover clean
code, multi-author history with a non-ASCII path, and recorded file limitations.
On macOS, each fixture passed a full-output double run and comparison against its
frozen output. Relocation also passed after replacing the two root-level
repository identities with the fixture ID. All other fields and list order were
retained; sorted-key compact UTF-8 JSON supplied the comparison bytes. The input
manifest has a separate SHA-256 so source changes are detected even when metrics
stay equal. Tests confirmed that changed inputs and changed expected outputs
are rejected.

This comparison projection is an M6 proposal for review with M5. Linux and
Windows runs and integration into the product canonical-output API remain open.

## Verification record

- Main CI at `ea6a47b`: Ubuntu, Python 3.10/3.11/3.12, successful;
  [workflow run](https://github.com/liuzhiyang5418/heatmap/actions/runs/43467734797).
- Local branch: macOS / Python 3.11, **232 passed and 1 skipped** in the full
  suite. The skipped test is the separately configured real-browser check. A
  separate run with headless Chrome passed **14 report and system tests**.
  Git's initial branch name was set to `master` for an existing test fixture.
- Main baseline quality audit with Ruff 0.17.5 and Mypy 2.4.1: `ruff check src
  tests` reported 19 findings; `mypy src/githotmap` reported 18 errors. These are
  tool-version-specific observations, not CI gate results.
- This branch's scoped Ruff and renderer-only Mypy commands passed locally.
  The new GitHub Actions job still needs a run on the submitted branch.

## Proposed schedule to Friday

| Date | Focus |
|---|---|
| Tuesday 17 Nov | Review the baseline, prepare the report panel and initial system checks, identify NFR-2 gaps, and record the confirmed target NFR pair. |
| Wednesday 18 Nov | Review M3/M4 diagnostics and fixed-clock work; M5 integrates their contracts; agree missing-file and encoding handling. |
| Thursday 19 Nov | Finish the fault suite and reproducibility contract, freeze inputs, run CI and retain results and screenshots. |
| Friday 20 Nov | Team reviews acceptance evidence and open exceptions; use the verified record and synthetic demo in the presentation. |

Record final acceptance against the reviewed commit, with the agreed criteria,
platform results, outstanding exceptions, and team sign-off.
