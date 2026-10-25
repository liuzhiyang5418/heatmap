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


def test_string_with_inline_comment():
    """行内有字符串 TODO 但行尾注释没有 TODO 时，不应误判。"""
    code = 'msg = "TODO: not a comment"  # regular comment\n'
    todos = list(iter_todos("a.py", code))
    assert len(todos) == 0


def test_string_and_inline_todo_comment():
    """行内有字符串 TODO 且行尾注释也有 TODO 时，只提取注释里的 TODO。"""
    code = 'msg = "TODO: not a comment"  # TODO: real comment\n'
    todos = list(iter_todos("a.py", code))
    assert len(todos) == 1
    assert todos[0].kind.value == "TODO"
    assert todos[0].description == "real comment"


def test_owner_extraction_paren():
    """TODO(责任人): 形式应解析出 owner。"""
    todos = list(iter_todos("a.py", "# TODO(alice): fix login\n"))
    assert len(todos) == 1
    assert todos[0].owner == "alice"
    assert todos[0].ref == ""


def test_owner_extraction_at():
    """TODO: 提及 @name 形式应解析出 owner。"""
    todos = list(iter_todos("a.py", "# TODO: refactor this @bob soon\n"))
    assert todos[0].owner == "bob"


def test_ref_extraction_hash():
    """TODO #123 形式应解析出带 # 前缀的 ref。"""
    todos = list(iter_todos("a.py", "# TODO #123: cleanup\n"))
    assert todos[0].ref == "#123"
    assert todos[0].owner == ""


def test_ref_extraction_ticket_paren():
    """TODO(HEATMAP-45): 工单号形态应识别为 ref 而非人名。"""
    todos = list(iter_todos("a.py", "# FIXME(HEATMAP-45): broken auth\n"))
    assert todos[0].ref == "HEATMAP-45"
    assert todos[0].owner == ""


def test_complex_paren_is_ignored():
    """既不像人名也不像工单号的括号内容不应被误判为 owner。"""
    todos = list(iter_todos("a.py", "# TODO: fix parser (see #123)\n"))
    assert todos[0].owner == ""
    assert todos[0].ref == "#123"


def test_severity_levels():
    """紧急/重要/常规关键词应解析出 3/2/1 三档 severity。"""
    assert next(iter(iter_todos("a.py", "# TODO: urgent fix\n"))).severity == 3
    assert next(iter(iter_todos("a.py", "# TODO: critical bug\n"))).severity == 3
    assert next(iter(iter_todos("a.py", "# TODO: important cleanup\n"))).severity == 2
    assert next(iter(iter_todos("a.py", "# TODO: maybe later\n"))).severity == 1


def test_meta_default_values():
    """无任何元信息时 owner/ref 为空串、severity 为 1。"""
    todo = next(iter(iter_todos("a.py", "# TODO: plain todo\n")))
    assert todo.owner == ""
    assert todo.ref == ""
    assert todo.severity == 1


def test_to_dict_contains_meta():
    """to_dict() 应包含 owner/ref/severity 三个新字段。"""
    todo = next(iter(iter_todos("a.py", "# TODO(alice) #123: urgent task\n")))
    payload = todo.to_dict()
    assert payload["owner"] == "alice"
    assert payload["ref"] == "#123"
    assert payload["severity"] == 3

