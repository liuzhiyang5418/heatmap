"""Exercise sorting, linkage and text handling in a real headless Chrome."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from githotmap.core.diagnostics import AnalysisStats, Degradation, DegradationCode
from githotmap.core.models import AnalysisResult, FileMetrics, FileResult
from githotmap.renderers import registry


def _chrome() -> str | None:
    configured = os.environ.get("HEATMAP_CHROME")
    if configured:
        return configured
    for name in ("google-chrome", "chromium", "chromium-browser"):
        executable = shutil.which(name)
        if executable:
            return executable
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return str(mac) if mac.exists() else None


def _sample_report() -> str:
    files = [
        FileResult(metrics=FileMetrics(path="z.py", lines_of_code=20, unique_contributors=2), mode_score=90),
        FileResult(metrics=FileMetrics(path="a.py", lines_of_code=10, unique_contributors=5),
                   mode_score=10, limitations=["syntax-error"]),
        FileResult(metrics=FileMetrics(path='<img data-xss="yes" src="x">.py', lines_of_code=1),
                   mode_score=0, status="missing", confidence=0),
    ]
    stats = AnalysisStats(
        files_matched=5, files_emitted=4, files_degraded=1, degradations_by_code={"syntax-error": 1},
        degradations=[Degradation(
            stage="scanner", code=DegradationCode.SYNTAX_ERROR, path="a.py",
            summary="Invalid syntax", detail='<img data-xss="diagnostic" src="x">',
        )],
    )
    return registry.render(
        AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot", files=files, stats=stats), "html",
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_report_interaction_logic_with_mock_dom(tmp_path: Path) -> None:
    page = tmp_path / "report.html"
    page.write_text(_sample_report(), encoding="utf-8")
    harness = Path(__file__).with_name("html_interactions.js")
    completed = subprocess.run([shutil.which("node"), str(harness), str(page)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_failed_collection_reports_unavailable_counts(tmp_path: Path) -> None:
    stats = AnalysisStats(degradations=[Degradation(
        stage="git", code=DegradationCode.STAGE_FAILED, path=None,
        summary="Collection failed", detail="injected failure",
    )])
    result = AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot", stats=stats)
    page = tmp_path / "failed.html"
    page.write_text(registry.render(result, "html"), encoding="utf-8")
    harness = Path(__file__).with_name("html_interactions.js")
    completed = subprocess.run(
        [shutil.which("node"), str(harness), str(page), "failed"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_limited_report_shows_reason_counts_for_hidden_files(tmp_path: Path) -> None:
    stats = AnalysisStats(
        files_matched=2, files_emitted=2, files_degraded=1,
        degradations_by_code={"syntax-error": 1},
    )
    result = AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot", stats=stats)
    page = tmp_path / "limited.html"
    page.write_text(registry.render(result, "html"), encoding="utf-8")
    harness = Path(__file__).with_name("html_interactions.js")
    completed = subprocess.run(
        [shutil.which("node"), str(harness), str(page), "limited"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_stage_failure_marks_file_cells_as_limited(tmp_path: Path) -> None:
    stats = AnalysisStats(degradations=[Degradation(
        stage="scanner", code=DegradationCode.STAGE_FAILED, path=None, summary="Scanner failed",
    )])
    files = [FileResult(metrics=FileMetrics(path="sample.py", lines_of_code=1), mode_score=20)]
    result = AnalysisResult(repo_path=".", repo_urn="local:test", mode="hot", files=files, stats=stats)
    page = tmp_path / "scanner-failed.html"
    page.write_text(registry.render(result, "html"), encoding="utf-8")
    harness = Path(__file__).with_name("html_interactions.js")
    completed = subprocess.run(
        [shutil.which("node"), str(harness), str(page), "failed-scanner"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(not os.environ.get("HEATMAP_CHROME"), reason="set HEATMAP_CHROME to run browser checks")
def test_report_interactions_in_browser(tmp_path: Path) -> None:
    html = _sample_report()
    checks = """<script>
try {
  const require = (condition, message) => { if (!condition) throw Error(message); };
  const rows = () => [...document.querySelectorAll('#tbody tr')];
  const cells = () => [...document.querySelectorAll('.cell')];
  const header = key => document.querySelector(`#table th[data-key="${key}"]`);
  header('path').click();
  const actual = rows().map(row => row.dataset.path);
  const expected = [...actual].sort((a,b) => a.localeCompare(b));
  require(JSON.stringify(actual) === JSON.stringify(expected), 'path sort');
  header('unique_contributors').click();
  require(rows()[0].dataset.path === 'a.py', 'contributors sort');
  header('lines_of_code').click();
  require(rows()[0].dataset.path === 'z.py', 'LOC sort');
  cells().find(cell => cell.dataset.path === 'a.py').click();
  require(rows().find(row => row.style.background).dataset.path === 'a.py', 'cell-row linkage');
  const missing = cells().find(cell => cell.dataset.path.includes('data-xss'));
  require(missing.style.background === 'rgb(119, 127, 139)', 'missing colour');
  require(cells().find(cell => cell.dataset.path === 'a.py').style.background === 'rgb(119, 127, 139)', 'limitation colour');
  missing.dispatchEvent(new Event('mouseenter'));
  require(!document.querySelector('img[data-xss]'), 'file path treated as HTML');
  require(document.querySelector('#tooltip').textContent.includes('Empty file or missing data'), 'status tooltip');
  require(document.querySelector('#coverage-summary').textContent.includes('Matched files5'), 'coverage counts');
  require(document.querySelector('#diagnostic-list').textContent.includes('syntax-error'), 'diagnostic code');
  require(document.querySelector('#reason-counts').textContent.includes('syntax-error: 1'), 'reason counts');
  document.querySelector('#diagnostic-list button').click();
  require(rows().find(row => row.style.background).dataset.path === 'a.py', 'diagnostic-row linkage');
  require(!document.querySelector('img[data-xss]'), 'diagnostic treated as HTML');
  document.body.dataset.uiTest = 'passed';
} catch (error) { document.body.dataset.uiTest = 'failed: ' + error.message; }
</script>"""
    page = tmp_path / "report.html"
    page.write_text(html.replace("</body>", checks + "</body>"), encoding="utf-8")
    completed = subprocess.run(
        [_chrome(), "--headless", "--disable-gpu", "--no-sandbox", "--disable-extensions",
         "--no-first-run", f"--user-data-dir={tmp_path / 'chrome-profile'}", "--dump-dom", page.as_uri()],
        capture_output=True, text=True, timeout=45, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert 'data-ui-test="passed"' in completed.stdout, completed.stdout[-2500:]
