"""Git 采集层解析器的单元测试（纯函数，不依赖真实仓库）。"""

from __future__ import annotations

from githotmap.core.git import GitLogParser


def test_parse_numstat_basic() -> None:
    text = (
        "\x01abc123\x01Alice\x011700000000\n"
        "10\t2\tsrc/main.py\n"
        "5\t0\tsrc/util.py\n"
        "\n"
        "\x01def456\x01Bob\x011700001000\n"
        "-\t-\timg.bin\n"
        "0\t3\tsrc/main.py\n"
    )
    records = GitLogParser().parse(text)
    assert len(records) == 4

    first = records[0]
    assert first.author == "Alice"
    assert first.timestamp == 1700000000
    assert first.file_path == "src/main.py"
    assert first.added == 10
    assert first.deleted == 2
    assert first.churn == 12

    binary = next(r for r in records if r.file_path == "img.bin")
    assert binary.churn == 0


def test_parse_empty_and_garbage_lines_ignored() -> None:
    text = (
        "random non-record line\n"
        "\x01hash\x01Carol\x011700000000\n"
        "\n"
        "\n"
        "3\t1\tpkg/mod.py\n"
    )
    records = GitLogParser().parse(text)
    assert len(records) == 1
    assert records[0].file_path == "pkg/mod.py"
    assert records[0].author == "Carol"
