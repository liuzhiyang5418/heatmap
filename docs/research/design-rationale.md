# Design Rationale and Implementation Boundaries

Status: research and design guidance; this is not evidence that a user study has been completed. The implementation description has been updated against the Sprint 1 working branch. Additions in that branch are not on main until merged.

## Goal

githotmap turns Git history and file size into explainable candidate signals to support discussion of maintenance hotspots and inspection or refactoring priorities. Technical debt also depends on future change and cost: TODOs, complex files, and high churn should not automatically be treated as confirmed debt. See the [literature review, P1–P6](literature-review.md).

## Current implementation and proposed extensions

| Area | Current implementation | Proposed extension / validation |
|---|---|---|
| Host and presentation | Standalone CLI, self-contained HTML, and JSON; the working branch adds an optional local Flask entry point. | Evolve within the existing Renderer protocol; the Flask entry point is a synchronous prototype. |
| Main pipeline | Git collection → metrics → worktree size → structural metrics and TODO counts → scoring → ranking and directory aggregation. | Scanner and TODO failures can silently fall back; details do not retain the original TODO text and line numbers. |
| Scanner | The scanner supplies structure, line counts, and parse status; the pipeline uses some structural metrics. | Propagate limitation reasons and coverage into analysis results and reports, following the [scanner interface](../scanner-interface.md). |
| `complexity` mode | Combines structural, size, age, and maintenance-activity signals. | The mode name does not mean AST cyclomatic complexity; scoring validity requires separate evaluation. |
| `roi` mode | A heuristic for refactoring priority. | It does not represent measured financial return, time saved, or actual repair benefit. |
| Heatmap | File cells, hover details, and a sortable table; cell area approximately reflects LOC; the working branch displays current status and confidence. | Directory hierarchy, path filtering, complete failure reasons, and comment evidence remain proposals. |

## Why retain the map, table, and details

A map can show spatial distribution, a table supports precise sorting, and details carry the underlying evidence. CodeCharta illustrates directory exploration, path search, and interpretable legends; P4 cautions that maps do not necessarily help exact lookup. The recommendation is to add directories and search incrementally to the current HTML report, not to rebuild a complete 3D system solely on the basis of this review.

Label cell area as file size, and identify the selected mode, score range, and measurement basis for color. If SATD is added later, show the source text, line number, and candidate status rather than just a count. Distinguish absent history, parsing failure, and zero values; small files must remain reachable via the table and search.

## Metric and interpretation limits

Current churn is added plus deleted lines; the original definition in P3 differs. The history start, recent window, and decay half-life are distinct parameters and should be explained separately. Worktree size and historical snapshots can differ and should be labeled explicitly.

High churn can result from new features, formatting, or bulk changes. High concentration alone does not prove a knowledge silo, and a long period without changes can indicate stability. Current scores combine signals whose validity is unproven; retain counterexamples and do not treat natural-language explanations as established causal relationships.

## Evaluation and stopping rules

Evaluate data correctness, candidate identification and ranking, and interface task performance separately. Correctly finding the top three shows that a user read the system's ranking; it does not prove that ranking reflects actual technical-debt priorities. Tasks, baselines, and scoring are described in the [evaluation plan](evaluation-plan.md).

Prioritize explanation and auditability. Co-change matrices, cross-version trends, 3D displays, and NLP training are extensions. Under P5's management taxonomy, the project mainly supports identification, proxy measurement, inspection prioritization, and communication; it does not promise to repay all kinds of technical debt automatically.
