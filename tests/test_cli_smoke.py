"""CLI 端到端冒烟：从 argparse 入口一路到磁盘产物（Sprint 3 / WP-S3-2.4）。

与已有测试的分工（避免重复）：

- ``test_html.py`` / ``test_json_renderer.py`` 测**渲染器本身**，输入是构造好的
  ``AnalysisResult``；
- ``test_nfr2_system.py`` 测**降级语义与 strict 判定**；
- 本文件只测**「命令行参数 → 流水线 → 渲染 → 写文件 → 退出码」这条真实路径**，
  确保参数解析、输出路由与退出码三者没有断链。此前这条路径是手工跑的。

退出码契约（``cli/main.py``）：

    0 成功   1 分析失败   2 配置/格式错误   3 严格模式下检测到降级
"""

from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

from githotmap import __version__
from githotmap.cli.main import main


def _repository(root: Path, files: dict[str, bytes]) -> Path:
    """建一个提交身份自包含的最小仓库（不依赖运行机器的全局 git 配置）。"""
    root.mkdir()
    with git.Repo.init(root) as repo:
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        repo.index.add(list(files))
        actor = git.Actor("Fixture", "fixture@example.invalid")
        repo.index.commit("add fixtures", author=actor, committer=actor)
    return root


def _clean_repo(root: Path) -> Path:
    return _repository(root / "clean", {"src/main.py": b"def f():\n    return 1\n"})


def _faulty_repo(root: Path) -> Path:
    return _repository(
        root / "faulty",
        {
            "src/ok.py": b"print(1)\n",
            "src/broken.py": b"def broken(:\n    pass\n",
        },
    )


# --------------------------------------------------------------------------- #
# 成功路径：两种输出格式都要真正落到磁盘
# --------------------------------------------------------------------------- #
def test_html_output_is_written_and_self_contained(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _clean_repo(tmp_path)
    out = tmp_path / "report.html"

    code = main(["analyze", "--repo-path", str(repo), "--output", "html", "--output-file", str(out)])

    assert code == 0
    assert out.is_file() and out.stat().st_size > 0
    html = out.read_text(encoding="utf-8")
    assert html.lstrip().startswith("<!doctype html>")
    # 数据必须内嵌（离线可打开），且不能引用外部资源
    assert "src/main.py" in html
    assert "<script src=" not in html
    assert "<link rel=\"stylesheet\"" not in html
    assert "已写出" in capsys.readouterr().out


def test_json_output_is_parseable_and_complete(tmp_path: Path) -> None:
    repo = _clean_repo(tmp_path)
    out = tmp_path / "report.json"

    code = main(["analyze", "--repo-path", str(repo), "--output", "json", "--output-file", str(out)])

    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert {"schema_version", "repo_path", "repo_urn", "mode", "analyzed_at", "files", "folders", "stats"} <= set(payload)
    assert payload["files"], "端到端跑通时至少应产出一个文件结果"
    assert {"files_matched", "files_emitted", "files_degraded", "degradations_by_code"} <= set(payload["stats"])


def test_default_html_output_path_is_used_when_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """不传 --output-file 时，html 应写到当前目录的 heatmap.html。"""
    repo = _clean_repo(tmp_path)
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    code = main(["analyze", "--repo-path", str(repo)])

    assert code == 0
    assert (workdir / "heatmap.html").is_file()


# --------------------------------------------------------------------------- #
# 严格模式：退出码 3 与 0 两条边
# --------------------------------------------------------------------------- #
def test_strict_mode_exits_3_on_faulty_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _faulty_repo(tmp_path)
    out = tmp_path / "strict.html"

    code = main(["analyze", "--repo-path", str(repo), "--strict", "--output-file", str(out)])

    assert code == 3
    assert not out.exists(), "严格模式下不应写出报告"
    stderr = capsys.readouterr().err
    assert "syntax-error" in stderr


def test_strict_mode_exits_0_on_clean_repo(tmp_path: Path) -> None:
    repo = _clean_repo(tmp_path)
    out = tmp_path / "strict-clean.html"

    code = main(["analyze", "--repo-path", str(repo), "--strict", "--output-file", str(out)])

    assert code == 0
    assert out.is_file()


# --------------------------------------------------------------------------- #
# 错误路径：配置/格式错误返回 2，不抛栈
# --------------------------------------------------------------------------- #
def test_unknown_output_format_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _clean_repo(tmp_path)

    code = main(["analyze", "--repo-path", str(repo), "--output", "no-such-format"])

    assert code == 2
    assert "no-such-format" in capsys.readouterr().err


def test_missing_repository_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """传入不存在的路径属配置错误，返回 2；不能降级成「0 个文件的成功报告」。"""
    code = main(["analyze", "--repo-path", str(tmp_path / "does-not-exist")])

    assert code == 2
    stderr = capsys.readouterr().err
    assert "不存在" in stderr


def test_file_path_instead_of_directory_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """传的是文件而不是目录，同样按配置错误处理。"""
    a_file = tmp_path / "a.py"
    a_file.write_text("print(1)\n", encoding="utf-8")

    code = main(["analyze", "--repo-path", str(a_file)])

    assert code == 2
    assert capsys.readouterr().err


# --------------------------------------------------------------------------- #
# 其它入口
# --------------------------------------------------------------------------- #
def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--version"])

    assert code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help_and_returns_0(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])

    assert code == 0
    assert "usage:" in capsys.readouterr().out
