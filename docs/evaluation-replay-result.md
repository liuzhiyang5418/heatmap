# Q2 result — historical replay (2026-11-23)

Method, metric definitions, sample-size guard and window-selection rule are frozen in
[`docs/evaluation-contract.md`](evaluation-contract.md) §11. This file only records **what
came out**, including the run that looks bad.

Executed 2026-11-23 on the team repository itself (`heatmap`), analyzer as of commit
`cbbfc80`, `--mode roi`, `--top-k 10`.

Reproduce with:

```bash
python examples/evaluation/historical_replay.py --repo . --from <t0> --to <t1> \
  --mode roi --top-k 10 --out replay.json
```

---

## 1. Primary window — one full iteration (`daf9500..HEAD`)

`daf9500` = Sprint 2 close; `HEAD` = `cbbfc80`. Window: **48 commits / 15.9 days**.

| Quantity | Value |
|---|---|
| Files scored at `t0` | 65 |
| Files changed in window | 60 |
| Comparable | 30 |
| Deleted in window | 0 |

| Metric | Value |
|---|---|
| Precision@10 | **90.0 %** (9/10) |
| Random baseline | 46.2 % (4.6/10) |
| **Lift** | **1.95×** |
| Recall@10 | 50.0 % |
| Spearman ρ | 0.2262 |

Reading it honestly:

- **Lift 1.95× is the real headline**, not the 90 %. In this window 30 of 65 scored files were
  touched, so a blind pick already hits 46 % of the time. The tool roughly doubled the hit
  rate of chance — useful, not transformative.
- **Recall@10 = 50 %** means the flag set held half of the ten heaviest-churn files. The two
  heaviest files (`core/pipeline.py`, 344 lines; `core/analysis.py`, 214 lines) were **not**
  in the top 10 — they ranked 11-ish by score. This is the tool's clearest weakness: it
  preferred historically hot but *quieter-in-this-window* files (`scoring.py` scored highest
  with 12 lines churn) over the files that were being rewritten.
- **Spearman ρ = 0.226** is weak positive monotonicity. Score magnitude is a poor predictor of
  how much a file will churn; the *set* is decent, the *order* inside it is not.

## 2. Sensitivity window — shortest available (`HEAD~8..HEAD`)

Same command, `t0 = d9223501`, window **15 commits / 1.9 days**.

| Quantity | Value |
|---|---|
| Files scored at `t0` | 85 |
| Files changed in window | 19 |
| Comparable | **9** |
| Deleted in window | 0 |

| Metric | Value |
|---|---|
| Precision@10 | 10.0 % (1/10) |
| Random baseline | 10.6 % (1.1/10) |
| **Lift** | **0.94×** |
| Recall@10 | 10.0 % |
| Spearman ρ | 0.05 |

**This run is reported as a failure, not dropped.** It triggered both sample-size guards
(`comparable = 9 < 2·K = 20`, and `comparable < K`, capping attainable Precision at 90 %).

What it demonstrates — and why it is more valuable than a second good number:

- Nine of the tool's top ten files had **zero churn** in the window. They were not mis-scored;
  this window simply edits documentation and the evaluation scripts under
  `examples/evaluation/`, which did not exist at `t0` and therefore cannot be scored.
- Historical-hotness signals update on the order of **weeks**. Window lengths below one
  iteration measure the gap between "what was hot" and "what this week's task happened to
  touch", which is mostly task assignment, not code health.
- Therefore the method's precondition is explicit: **window ≥ one iteration, and the window's
  work must be product code**. A replay over a documentation-only window answers nothing.

## 3. What the two runs jointly support

Supportable claims:

1. Over an iteration-length window of real product work, the flag set contains
   substantially more of the actually-churned files than chance does (Lift 1.95×).
2. The ranking is **not** a reliable ordering by future churn (ρ ≈ 0.23, and the two heaviest
   files sat outside the top ten).

Not supportable, and never to be stated:

- That acting on the list reduces defects, effort or review time.
- That a developer reads the map faster or decides better (that is Q3, which is **open**).
- That the score measures technical debt.
- That 90 % is "accuracy" — it is overlap with a 46 % baseline on a 30-file comparable set.

## 4. Threats to validity

| Threat | Effect | Mitigation |
|---|---|---|
| Single repository, single window | Cannot generalise across projects | Disclosed; the metric is descriptive, not inferential |
| Retrospective, not causal | Overlap ≠ benefit | Stated in every reported figure |
| `--no-renames` splits renames into delete+add | Inflates churn for renamed files | Fixed flag; renames were rare here (0 deletions) |
| Churn counts generated code / docs | A busy generated file can outrank real logic | Restricting to source paths is future work, not done here |
| `t0` analyzer is the current `HEAD` checkout at `t0` | Uses today's analyzer on an old snapshot by design (we evaluate the tool, not the history) | Documented; the analyzer's own version is the subject, not held fixed |
| Short windows produce unstable ratios | Noise can look like a result | §11.3 guard emits warnings; such runs are not conclusions |

## 5. Reproduce / archive

Raw JSON from both runs is regenerable with the command in the header; the numbers in this
document are the archive. `generated_at` in each JSON records when it was produced, so a
regenerated file is never mistaken for the original observation.
