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
        "155089b094f499314774c3cc0e36771d5e2c1ebfa4dc80569313e4c69e59c32c",
        "bee9357345067482412ba92499874d835d08f2fd76b5667fc5a447b8c10e1802",
        "f887b373c2243b32d0867f0dc99cba25aa2c71857cfe0f961e7bce0dd837dfbe",
    ]


def test_frozen_snapshot_fingerprint_is_independent_of_checkout_path(tmp_path: Path) -> None:
    files = {"src/a.py": "print(1)\n", "src/b.py": "x = 2\n"}
    left = _snapshot(tmp_path / "left", files)
    right = _snapshot(tmp_path / "right", files)
    assert AnalysisPipeline(clock=_CLOCK).run(left).fingerprint() == AnalysisPipeline(clock=_CLOCK).run(right).fingerprint()
