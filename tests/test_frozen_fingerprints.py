"""Frozen synthetic Git snapshots for the NFR-3 reproducibility contract."""

from __future__ import annotations

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
    (root / ".gitattributes").write_text("* text eol=lf\n", encoding="utf-8")
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_DATE="2029-01-01T00:00:00Z", GIT_COMMITTER_DATE="2029-01-01T00:00:00Z")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Frozen", "-c", "user.email=frozen@example.invalid", "commit", "-qm", "snapshot"],
        check=True, env=env,
    )
    if second_commit:
        (root / next(iter(files))).write_text(next(iter(files.values())) + "\n# follow-up\n", encoding="utf-8")
        env = dict(env, GIT_AUTHOR_DATE="2029-06-01T00:00:00Z", GIT_COMMITTER_DATE="2029-06-01T00:00:00Z")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=Frozen", "-c", "user.email=frozen@example.invalid", "commit", "-qm", "follow-up"],
            check=True, env=env,
        )
    return root


def test_three_frozen_snapshots_have_stable_fingerprints(tmp_path: Path) -> None:
    snapshots = [
        _snapshot(tmp_path / "one", {"src/a.py": "print(1)\n"}),
        _snapshot(tmp_path / "two", {"src/a.py": "print(1)\n", "src/b.py": "x = 2\n"}),
        _snapshot(tmp_path / "three", {"src/a.py": "print(1)\n", "README.md": "fixture\n"}, second_commit=True),
    ]
    fingerprints = [AnalysisPipeline(clock=_CLOCK).run(path).fingerprint() for path in snapshots]
    assert fingerprints == [
        "aa59c81e3a0d9bb3888eb3f376362dbb9041bbd4d8ec788d4be0ad164cb98499",
        "3c748e49ac1d6d1d5a0c0f82cb688c870caa39fa912f5e4eb83296f6198d4512",
        "d851c92d0be4b2e1759c111f78fbac292a684769e68694cf4543631b562551b3",
    ]


def test_frozen_snapshot_fingerprint_is_independent_of_checkout_path(tmp_path: Path) -> None:
    files = {"src/a.py": "print(1)\n", "src/b.py": "x = 2\n"}
    left = _snapshot(tmp_path / "left", files)
    right = _snapshot(tmp_path / "right", files)
    assert AnalysisPipeline(clock=_CLOCK).run(left).fingerprint() == AnalysisPipeline(clock=_CLOCK).run(right).fingerprint()
