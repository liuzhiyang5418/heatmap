# githotmap — Git Technical Debt Heatmap and Prioritization

githotmap turns Git commit metadata into measurable, sortable, visual signals that help teams inspect the distribution of potential maintenance hotspots and discuss refactoring and knowledge-sharing priorities.

This is a CS5351 software engineering group project. It is a standalone Python CLI with a core engine separated from its renderers and hosts.

## Approach

The tool analyzes development activity alongside file structure and size:

```text
Git history
   │  GitPython traverses commits and reads per-file statistics
   ▼
Raw commits ──► Aggregated metrics (commits, churn, contributor Gini, age, size, LOC, recency decay)
   │
   ▼
Scoring engine (4 modes + 3 composite modes; scores from 0–100, breakdowns, and explanations)
   │
   ▼
Prioritized files ──► Renderer (interactive HTML heatmap by default; replaceable)
```

## Scoring modes

| Mode | Purpose | Main signals |
|---|---|---|
| `hot` | Activity hotspots | Recent commits, churn, active development |
| `risk` | Knowledge concentration and bus-factor risk | Contributor concentration, uneven ownership, potential knowledge silos |
| `complexity` | Structural debt candidates | AST structure (cyclomatic complexity, nesting depth, symbol count), SATD density, churn and age |
| `roi` | Heuristic refactoring priority | High churn on large files |

Composite modes:

| Mode | Weights | Intended use |
|---|---|---|
| `active_owners` | hot 50% + risk 50% | Identify active changes with concentrated ownership for knowledge sharing |
| `refactor_now` | complexity 60% + roi 40% | Discuss refactoring priority during sprint planning |
| `legacy_debt` | complexity 70% + risk 30% | Inspect concentrated legacy areas before change |

Each file result includes `recency_signal` and dynamic thresholds to help distinguish an active frontier from a historical hotspot.

## Relationship to the reference implementation

The **scoring semantics of three base modes** — `hot`, `risk` and `roi`, including their weights, the normalisation caps, the exponential time decay and the debuff rules — are aligned with the open-source Go tool [`huangsam/hotspot`](https://github.com/huangsam/hotspot) (MIT, © 2025 Samuel Huang). This alignment is deliberate and the version is recorded, so that those three modes remain comparable between the two tools. The fourth mode and the composite weights borrow only the naming and the blend ratios.

githotmap is **not a fork or a port** of that project: it is a separate Python codebase, and the scanner (AST structure), TODO/SATD detection, renderers, reason-code diagnostics and deterministic fingerprints have no counterpart there.

One mode is **not** comparable. `complexity` keeps the name but uses a different metric set — AST structure and SATD density rather than file size and staleness — so its scores, and those of the `refactor_now` / `legacy_debt` composites built on it, must not be compared across the two tools.

Item-by-item comparison, including which weights are identical and what we changed on purpose: [docs/research/reference-alignment.md](docs/research/reference-alignment.md).

## Quick start

```bash
# Install in editable mode
cd heatmap
pip install -e .

# Run as a module after installation
python -m githotmap analyze --repo-path . --mode roi --output html --output-file heatmap.html

# Export machine-readable metrics, score breakdowns, and statuses
python -m githotmap analyze --repo-path . --mode roi --output json --output-file heatmap.json

# Show help
python -m githotmap --help
python -m githotmap analyze --help
```

The generated `heatmap.html` is a self-contained interactive report with no external CDN. Hover over a cell for file details and scoring explanations; click table headers to sort. Cell area approximately reflects LOC and color reflects the selected mode's score. Gray indicates the model's `missing` status, which currently combines empty and missing files and requires manual review.

### Local web entry point

```bash
pip install -e '.[web]'
githotmap serve --port 5000
```

Open `http://127.0.0.1:5000`, enter a local Git repository path, and select a mode. The form invokes the existing pipeline synchronously and displays the HTML report. It binds to loopback and has no background jobs, directory filtering, or upload support. The CLI and offline report work without the `web` extra.

## Repository layout

```text
heatmap/
├── pyproject.toml              # Packaging and tool configuration
├── README.md
├── src/githotmap/
│   ├── __init__.py             # Version and public API
│   ├── __main__.py             # python -m githotmap entry point
│   ├── clock.py                # Injectable clock — all time sources live here (NFR-3)
│   ├── cli/main.py             # argparse CLI (analyze / history / serve)
│   ├── core/                   # Models, Git collection, metrics, scoring, ranking, pipeline
│   │   └── diagnostics.py      # Degradation codes and coverage statistics (NFR-2)
│   ├── renderers/              # Renderer protocol, registry, HTML and JSON renderers
│   ├── scanner/                # Repository scanner: file discovery + AST structure (M2)
│   ├── todo/                   # TODO/FIXME/HACK/XXX detection (M3)
│   ├── web/                    # Optional local Flask entry point
│   ├── config/config.py        # Default weights, thresholds, and presets
│   └── plugins/base.py         # Reserved plugin extension protocol
├── docs/                       # Interfaces, NFR scope, evaluation contract, sprint records
├── tests/                      # Unit, robustness, determinism and system tests
└── examples/demo.py            # Programmatic usage example
```

## Architecture and extensibility

The core engine (`core/`) produces structured `AnalysisResult` data without depending on a renderer or host. Renderers implement `renderers.base.Renderer` and are registered and selected through `renderers.registry`. New formats can be added through that protocol without changing the core pipeline.

Layering, the **load-bearing dependency rules**, and a full **contract index** (which doc defines what, who consumes it, which test would fail if it drifted) live in [docs/architecture.md](docs/architecture.md). The build / test / submit workflow and this project's known pitfalls are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Development

```bash
pip install -e '.[dev]'
pytest                 # Run tests
ruff check src tests   # Lint
mypy src               # Type check
```

To run the browser interaction test, set `HEATMAP_CHROME` to a local Chrome or Chromium executable and run `pytest tests/test_html_browser.py`. The environment must permit launching a separate headless browser.

The [Sprint 1 record](docs/sprint-1.md) covers user stories, proposed architecture, acceptance status, and team decisions still needed.

The **frozen NFR scope** — NFR-2 robustness/auditability and NFR-3 reproducibility, with metrics, architecture decisions, exclusions and open sign-offs — is defined in [docs/nfr.md](docs/nfr.md). Implementation notes and the 2026-11-18 decision log (D-1…D-3) live in [docs/nfr2-nfr3.md](docs/nfr2-nfr3.md). The evaluation contract ([docs/evaluation-contract.md](docs/evaluation-contract.md), v1.1) separates three questions: Q1 data correctness is covered by the test suite, Q2 ranking relevance was answered by **historical replay** against real commit windows, and Q3 interface effect (a participant study) was **dropped, not executed** — that question is reported as open, not as answered by proxy.

CI runs the full test matrix (Ubuntu + Windows × Python 3.10–3.12) and a **whole-repository** `ruff` + `mypy` gate on every push and pull request.

## Research and evaluation

The [research index](docs/research/README.md) links the initial six-paper comparison, design rationale, open-source tool observations, and a planned evaluation.

Scores are heuristic signals for inspection and prioritization; they do not establish technical debt, defect probability, repair effort, or financial return. The `complexity` mode is a **composite** of several signals; its 0–100 score is not an AST cyclomatic complexity value, even though cyclomatic complexity is one of its inputs. The pipeline counts TODO candidates but does not show the original comments or line numbers. Pipeline failures are exposed as degradation diagnostics; legacy deep-history functions warn for empty or shallow repositories, while their `*_with_degradations` counterparts return structured reasons. Results reported in research papers are not evidence that this project achieved the same effects.
