"""Frozen synthetic Git snapshots for the NFR-3 reproducibility contract."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from githotmap.clock import FixedClock
from githotmap.core.pipeline import AnalysisPipeline

_CLOCK = FixedClock(datetime(2030, 1, 1, tzinfo=timezone.utc))


def _snapshot(root: Path, files: dict[str, str], *, second_commit: bool = False) -> Path:
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "false"], check=True)
    (root / ".gitattributes").write_text("* text eol=lf\n", encoding="utf-8", newline="\n")
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # 必须显式 newline="\n"：Windows 上 write_text 默认把 \n 写成 \r\n，
        # 而 size_bytes 参与指纹，会让两个平台生成的字节数不同、摘要必然对不上。
        path.write_text(content, encoding="utf-8", newline="\n")
    env = dict(os.environ, GIT_AUTHOR_DATE="2029-01-01T00:00:00Z", GIT_COMMITTER_DATE="2029-01-01T00:00:00Z")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Frozen", "-c", "user.email=frozen@example.invalid", "commit", "-qm", "snapshot"],
        check=True, env=env,
    )
    if second_commit:
        first = next(iter(files))
        (root / first).write_text(
            next(iter(files.values())) + "\n# follow-up\n", encoding="utf-8", newline="\n"
        )
        env = dict(env, GIT_AUTHOR_DATE="2029-06-01T00:00:00Z", GIT_COMMITTER_DATE="2029-06-01T00:00:00Z")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=Frozen", "-c", "user.email=frozen@example.invalid", "commit", "-qm", "follow-up"],
            check=True, env=env,
        )
    return root


_BASELINE = Path(__file__).with_name("fixtures") / "frozen_fingerprints.json"


def _load_baseline() -> dict[str, str]:
    """读取提交在仓库里的指纹基线（两个平台共同断言的同一份）。"""
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["fingerprints"]


def test_three_frozen_snapshots_have_stable_fingerprints(tmp_path: Path) -> None:
    snapshots = [
        _snapshot(tmp_path / "one", {"src/a.py": "print(1)\n"}),
        _snapshot(tmp_path / "two", {"src/a.py": "print(1)\n", "src/b.py": "x = 2\n"}),
        _snapshot(tmp_path / "three", {"src/a.py": "print(1)\n", "README.md": "fixture\n"}, second_commit=True),
    ]
    fingerprints = [AnalysisPipeline(clock=_CLOCK).run(path).fingerprint() for path in snapshots]
    assert all(len(value) == 64 and int(value, 16) >= 0 for value in fingerprints)
    # 双跑一致：同一快照、同一注入时钟，两次结果必须相同。
    assert [AnalysisPipeline(clock=_CLOCK).run(path).fingerprint() for path in snapshots] == fingerprints


def test_fingerprints_match_committed_baseline(tmp_path: Path) -> None:
    """与仓库内的基线摘要逐字节一致——这是「跨平台相同」的实际执行方式。

    ubuntu 与 windows 的 CI 都跑这条断言、对着同一份 ``frozen_fingerprints.json``，
    任一平台出现平台相关漂移（换行、路径分隔符、时间字段泄漏）都会让该平台失败。
    若要更新基线，必须同时提升 ``schema_version`` 并在提交信息里写明原因。
    """
    snapshots = {
        "one": _snapshot(tmp_path / "one", {"src/a.py": "print(1)\n"}),
        "two": _snapshot(tmp_path / "two", {"src/a.py": "print(1)\n", "src/b.py": "x = 2\n"}),
        "three": _snapshot(
            tmp_path / "three", {"src/a.py": "print(1)\n", "README.md": "fixture\n"},
            second_commit=True,
        ),
    }

    actual = {name: AnalysisPipeline(clock=_CLOCK).run(path).fingerprint() for name, path in snapshots.items()}

    assert actual == _load_baseline()


def test_frozen_snapshot_fingerprint_is_independent_of_checkout_path(tmp_path: Path) -> None:
    files = {"src/a.py": "print(1)\n", "src/b.py": "x = 2\n"}
    left = _snapshot(tmp_path / "left", files)
    right = _snapshot(tmp_path / "right", files)
    assert AnalysisPipeline(clock=_CLOCK).run(left).fingerprint() == AnalysisPipeline(clock=_CLOCK).run(right).fingerprint()
