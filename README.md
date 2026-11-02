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
| `complexity` | Technical-debt candidates | Large, old files with maintenance activity |
| `roi` | Heuristic refactoring priority | High churn on large files |

Composite modes:

| Mode | Weights | Intended use |
|---|---|---|
| `active_owners` | hot 50% + risk 50% | Identify active changes with concentrated ownership for knowledge sharing |
| `refactor_now` | complexity 60% + roi 40% | Discuss refactoring priority during sprint planning |
| `legacy_debt` | complexity 70% + risk 30% | Inspect concentrated legacy areas before change |

Each file result includes `recency_signal` and dynamic thresholds to help distinguish an active frontier from a historical hotspot.

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
│   ├── cli/main.py             # argparse CLI
│   ├── core/                   # Models, Git collection, metrics, scoring, ranking, pipeline
│   ├── renderers/              # Renderer protocol, registry, HTML, and JSON
│   ├── web/                    # Optional local Flask entry point
│   ├── config/config.py        # Default weights, thresholds, and presets
│   └── plugins/base.py         # Reserved plugin extension protocol
├── tests/                      # Unit and system tests and fixtures
└── examples/demo.py            # Programmatic usage example
```

## Architecture and extensibility

The core engine (`core/`) produces structured `AnalysisResult` data without depending on a renderer or host. Renderers implement `renderers.base.Renderer` and are registered and selected through `renderers.registry`. New formats can be added through that protocol without changing the core pipeline.

## Development

```bash
pip install -e '.[dev]'
pytest                 # Run tests
ruff check src tests   # Lint
mypy src               # Type check
```

To run the browser interaction test, set `HEATMAP_CHROME` to a local Chrome or Chromium executable and run `pytest tests/test_html_browser.py`. The environment must permit launching a separate headless browser.

The [Sprint 1 record](docs/sprint-1.md) covers user stories, proposed architecture, acceptance status, and team decisions still needed.

## Research and evaluation

The [research index](docs/research/README.md) links the initial six-paper comparison, design rationale, open-source tool observations, and a planned evaluation.

Scores are heuristic signals for inspection and prioritization; they do not establish technical debt, defect probability, repair effort, or financial return. The `complexity` mode combines several signals and is not AST cyclomatic complexity. The pipeline counts TODO candidates but does not show the original comments or line numbers; scanner or detection failures can still silently fall back. Results reported in research papers are not evidence that this project achieved the same effects.
