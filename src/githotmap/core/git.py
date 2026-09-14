"""Git 数据采集层：运行 ``git`` 命令并以单次 log 遍历提取提交元数据。

设计要点（对齐参考工具 hotspot 的单遍扫描策略）：

- 只做**一次** ``git log --numstat`` 遍历，同时拿到提交数、改动量、作者与时间，
  避免对同一历史反复 I/O；
- 提交头使用 ``\\x01``（SOH）作为字段分隔符，避免与作者名/路径中的制表符冲突；
- 解析结果产出与具体仓库无关的 :class:`CommitRecord` 列表，供 ``metrics`` 层聚合。

已知边界（留待后续 Sprint 处理）：暂不启用重命名检测（``-M``）、不解析 C 风格
转义的引号路径、二进制文件按 0 行改动计。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# 提交头在 git log 输出中的字段分隔符（SOH，几乎不可能出现在正常元数据中）。
_HEADER_SEP = "\x01"


class GitError(RuntimeError):
    """Git 命令执行失败时抛出，携带 stderr 以便诊断。"""


@dataclass(slots=True)
class CommitRecord:
    """单个提交对单个文件的一次改动记录。"""

    author: str
    timestamp: int  # 作者时间，unix 秒
    file_path: str
    added: int
    deleted: int

    @property
    def churn(self) -> int:
        return self.added + self.deleted


def run_git(args: Sequence[str], repo_path: str | Path) -> str:
    """以 UTF-8 执行一个只读 git 命令并返回 stdout；失败时抛 :class:`GitError`。

    注意：此处使用 ``subprocess.run(..., capture_output=True)`` 捕获输出；在受限
    沙箱（禁止命名管道）下调用方应改用 ``stdio`` 直通或提供 mock。作为库代码，
    该实现面向正常本机环境。
    """
    repo = str(repo_path)
    command = ["git", "-C", repo, *args]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:  # 例如 git 不在 PATH
        raise GitError(f"无法执行 git（{exc}），请确认已安装 Git 2.2+ 并加入 PATH") from exc

    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} 失败（exit {proc.returncode}）: {proc.stderr.strip()}")

    return proc.stdout


def resolve_urn(repo_path: str | Path) -> str:
    """解析仓库的可移植身份标识（URN）。

    优先使用远端 origin URL（规范化为 ``git:host/owner/repo`` 形态），否则回退到
    本地绝对路径 ``local:<abs_path>``，保证跨机器缓存键稳定。
    """
    repo = str(repo_path)
    try:
        url = run_git(["config", "--get", "remote.origin.url"], repo).strip()
    except GitError:
        url = ""
    if url:
        return f"git:{url.rstrip('/')}"
    return f"local:{Path(repo).resolve()}"


class GitLogParser:
    """把 ``git log --numstat`` 的文本输出解析为 :class:`CommitRecord` 列表。"""

    _LOG_ARGS: list[str] = [
        "log",
        "--numstat",
        "--date=unix",
        # 提交头：SOH 分隔  hash / 作者 / unix 时间，并以换行结束，确保 numstat 独占行。
        f"--pretty=format:{_HEADER_SEP}%H{_HEADER_SEP}%an{_HEADER_SEP}%at%n",
    ]

    def build_command(self, since: str | None = None) -> list[str]:
        args = list(self._LOG_ARGS)
        if since:
            args.append(f"--since={since}")
        return args

    def parse(self, text: str) -> list[CommitRecord]:
        records: list[CommitRecord] = []
        author = ""
        timestamp = 0

        for raw_line in text.splitlines():
            if raw_line.startswith(_HEADER_SEP):
                parts = raw_line[len(_HEADER_SEP) :].split(_HEADER_SEP)
                if len(parts) >= 3:
                    author = parts[1]
                    try:
                        timestamp = int(parts[2])
                    except ValueError:
                        timestamp = 0
                continue

            if not raw_line.strip():
                continue

            # numstat 行：added \t deleted \t path（二进制文件为 "- \t - \t path"）。
            fields = raw_line.split("\t", 2)
            if len(fields) < 3:
                continue
            added_s, deleted_s, path = fields[0], fields[1], fields[2]
            if not path:
                continue
            added = _parse_count(added_s)
            deleted = _parse_count(deleted_s)
            records.append(
                CommitRecord(
                    author=author,
                    timestamp=timestamp,
                    file_path=path,
                    added=added,
                    deleted=deleted,
                )
            )
        return records


def _parse_count(token: str) -> int:
    """numstat 计数可能是整数，也可能是二进制文件的 ``-``。"""
    token = token.strip()
    if token == "-":
        return 0
    try:
        return int(token)
    except ValueError:
        return 0


class GitHistory:
    """面向仓库的高层采集门面：运行命令并解析为提交记录。"""

    def __init__(self) -> None:
        self._parser = GitLogParser()

    def collect(self, repo_path: str | Path, since: str | None = None) -> list[CommitRecord]:
        """遍历仓库历史并返回全部（或 ``since`` 之后）的提交记录。"""
        args = self._parser.build_command(since=since)
        stdout = run_git(args, repo_path)
        return self._parser.parse(stdout)
