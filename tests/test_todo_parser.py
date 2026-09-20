"""``githotmap.todo.parser`` 的单元测试。

覆盖：单行注释、大小写、一行多标记、字符串内假标记排除、
docstring 提取、行列号、空源码、语法错误容错。
"""

from __future__ import annotations

from githotmap.todo.parser import iter_todos


def test_single_line_comment():
    """单行 # 注释中的 TODO 应被提取。"""
    todos = list(iter_todos("a.py", "# TODO: fix this\nx = 1\n"))
    assert len(todos) == 1
    assert todos[0].kind.value == "TODO"
    assert todos[0].lineno == 1
    assert todos[0].description == "fix this"


def test_case_insensitive():
    """大小写不敏感：todo / Todo / TODO 都应识别，kind 统一为大写。"""
    todos = list(iter_todos("a.py", "# todo\n# Todo\n# TODO\n"))
    assert len(todos) == 3
    assert all(t.kind.value == "TODO" for t in todos)


def test_multiple_markers_in_one_line():
    """同一行出现多个标记应逐一提取。"""
    todos = list(iter_todos("a.py", "# TODO then FIXME\n"))
    assert len(todos) == 2
    assert todos[0].kind.value == "TODO"
    assert todos[1].kind.value == "FIXME"


def test_string_not_comment():
    """字符串字面量里的 TODO 不应被误判为技术债注释。"""
    todos = list(iter_todos("a.py", 'msg = "TODO: not a comment"\n'))
    assert len(todos) == 0


def test_docstring():
    """docstring 里的标记应被提取。"""
    code = '"""TODO: module docstring"""\nx = 1\n'
    todos = list(iter_todos("a.py", code))
    assert len(todos) == 1
    assert todos[0].kind.value == "TODO"


def test_line_and_column():
    """行号与列号应正确（1 起）。"""
    todos = list(iter_todos("a.py", "  # TODO: x\n"))
    assert len(todos) == 1
    assert todos[0].lineno == 1
    assert todos[0].column == 5  # "  # " 共 4 个字符，TODO 从第 5 列开始


def test_comment_after_code():
    """行尾注释也应被提取（代码行后跟 # TODO）。"""
    todos = list(iter_todos("a.py", "x = 1  # HACK: quick fix\n"))
    assert len(todos) == 1
    assert todos[0].kind.value == "HACK"
    assert todos[0].lineno == 1


def test_empty_source():
    """空源码不产生任何条目且不报错。"""
    assert list(iter_todos("a.py", "")) == []


def test_syntax_error_source():
    """语法错误的源码不应抛异常，仍能提取可识别的注释。"""
    todos = list(iter_todos("a.py", "def broken(:\n# TODO: keep\n"))
    assert isinstance(todos, list)
    assert any(t.kind.value == "TODO" for t in todos)
