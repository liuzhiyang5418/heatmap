"""性能回归守卫（Sprint 3 / WP-S3-2.2）。

**守什么、不守什么**：本文件守「没有引入超线性或有明显灾难性代价的行为」，
不守「跑得多快」。原因是 CI 跑在 ubuntu + windows 的共享 runner 上，机器性能
不可控——把绝对秒数写成门禁，最后只会得到一堆 flaky 失败，然后被迫把阈值
放宽到没有意义。

因此用两个**与机器速度无关**的度量：

1. **伸缩性**：文件数变成 4 倍时，耗时不应超过 8 倍。线性算法约 4 倍，
   O(n²) 约 16 倍；8 倍这个位置能稳定区分两者，又不会被常数项干扰。
2. **绝对上界**：只做「灾难守卫」——400 文件仓库必须在 60 秒内完成。
   本机基线约 5 秒，留 12 倍缓冲，慢机器也不可能误报。

已知基线（Sprint 2 收口，`docs/nfr.md` §5）：本仓库 85 文件 / 3.90 s，
其中 git 采集占 93.3%；scanner 3.7% + todo 2.1% 是 NFR-2 的新增代价。

这些用例标了 ``slow``：CI 只在 Linux/Python 3.11 的单一组合上执行，
避免 6 个矩阵组合都重复跑一遍性能测量。
"""

from __future__ import annotations

import statistics
import subprocess
import time
from pathlib import Path

import pytest

from githotmap.core.pipeline import AnalysisPipeline

pytestmark = pytest.mark.slow


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _synthetic_repo(root: Path, n_files: int, n_commits: int = 2) -> Path:
    """建一个规模可控的仓库：n_files 个 Python 文件，分 n_commits 次提交。"""
    root.mkdir(parents=True)
    _git(root, "init", "-q", ".")
    for index in range(n_files):
        body = "".join(f"def f{index}_{j}(x):\n    return x + {j}\n" for j in range(4))
        (root / f"mod{index:04d}.py").write_text(body, encoding="utf-8")
    _commit(root, "init")
    for revision in range(1, n_commits):
        for index in range(0, n_files, 4):
            path = root / f"mod{index:04d}.py"
            path.write_text(
                path.read_text(encoding="utf-8") + f"\n# rev {revision}\n", encoding="utf-8"
            )
        _commit(root, f"rev{revision}")
    return root


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=Perf",
        "-c",
        "user.email=perf@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )


def _median_runtime(repo: Path, reps: int = 2) -> float:
    """重复分析取中位数，降低单次抖动的影响。"""
    samples: list[float] = []
    for _ in range(reps):
        started = time.perf_counter()
        AnalysisPipeline().run(repo, limit=100_000)
        samples.append(time.perf_counter() - started)
    return statistics.median(samples)


def test_analysis_scales_sublinearly(tmp_path: Path) -> None:
    """4 倍文件数的耗时应在 8 倍以内（线性≈4×，O(n²)≈16×）。"""
    small = _synthetic_repo(tmp_path / "small", 100)
    large = _synthetic_repo(tmp_path / "large", 400)

    t_small = _median_runtime(small, reps=2)
    t_large = _median_runtime(large, reps=2)

    if t_small < 0.05:
        pytest.skip(f"基准耗时 {t_small:.3f}s 太短，比值噪声过大，无法判定伸缩性")

    ratio = t_large / t_small
    assert ratio < 8.0, (
        f"文件数 4 倍（100→400）时耗时增长 {ratio:.1f} 倍"
        f"（{t_small:.2f}s → {t_large:.2f}s），疑似引入超线性行为"
    )


def test_analysis_completes_within_generous_bound(tmp_path: Path) -> None:
    """灾难守卫：400 文件仓库必须在 60 秒内完成（本机基线约 5 秒）。"""
    repo = _synthetic_repo(tmp_path / "repo", 400)

    elapsed = _median_runtime(repo, reps=1)

    assert elapsed < 60.0, f"400 文件分析耗时 {elapsed:.1f}s，超过 60s 的灾难上界"


def test_stage_timings_cover_every_stage(tmp_path: Path) -> None:
    """阶段耗时表必须完整——它是定位性能回归的唯一入口。"""
    repo = _synthetic_repo(tmp_path / "repo", 40)

    result = AnalysisPipeline().run(repo)

    assert set(result.stats.stage_elapsed_ms) == {
        "git",
        "metrics",
        "scanner",
        "todo",
        "scoring",
    }
    assert all(ms >= 0.0 for ms in result.stats.stage_elapsed_ms.values())
