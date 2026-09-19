"""Python 结构解析层（``githotmap.scanner.parser``）的单元测试。"""

from __future__ import annotations

from githotmap.scanner.models import SymbolInfo
from githotmap.scanner.parser import (
    ParsedSource,
    classify_lines,
    count_lines_plain,
    extract_imports,
    extract_symbols,
    parse_python_source,
)


def _symbol(parsed: ParsedSource, name: str) -> SymbolInfo:
    """按名字取出唯一符号，找不到或是重复即断言失败。"""
    matches = [symbol for symbol in parsed.symbols if symbol.name == name]
    assert len(matches) == 1, f"期望唯一符号 {name}，实际 {len(matches)} 个"
    return matches[0]


# --------------------------------------------------------------------------- #
# 行数统计
# --------------------------------------------------------------------------- #
SAMPLE = '''"""模块文档字符串。"""

import os


# 整行注释
def hello(name):
    """函数文档字符串。"""
    if not name:
        return "world"  # 行尾注释
    return name
'''


def test_classify_lines_buckets() -> None:
    parsed = parse_python_source(SAMPLE)
    counts = parsed.lines
    assert counts.total == 11
    assert counts.docstring == 2
    assert counts.blank == 3
    assert counts.comment == 1
    assert counts.code == 5


def test_line_counts_invariant() -> None:
    counts = parse_python_source(SAMPLE).lines
    assert counts.total == counts.code + counts.comment + counts.docstring + counts.blank


def test_hash_inside_string_is_not_a_comment() -> None:
    """词法分类的关键差异：字符串里的井号不是注释（正则方案会误判）。"""
    counts = classify_lines('COLOR = "#ff0000"\n', set())
    assert counts.comment == 0
    assert counts.code == 1


def test_trailing_comment_counts_as_code() -> None:
    counts = classify_lines("x = 1  # 说明\n", set())
    assert counts.code == 1
    assert counts.comment == 0


def test_blank_line_inside_docstring_counts_as_docstring() -> None:
    source = 'def f():\n    """第一行\n\n    第三行\n    """\n    return 1\n'
    counts = parse_python_source(source).lines
    assert counts.total == 6
    assert counts.docstring == 4
    assert counts.code == 2
    assert counts.blank == 0


def test_count_lines_plain_only_splits_blank_and_code() -> None:
    counts = count_lines_plain("a = 1\n\n\nb = 2\n")
    assert counts.total == 4
    assert counts.blank == 2
    assert counts.code == 2
    assert counts.comment == 0
    assert counts.docstring == 0


def test_empty_source() -> None:
    parsed = parse_python_source("")
    assert parsed.symbols == []
    assert parsed.imports == []
    assert parsed.lines.total == 0
    assert parsed.parse_error is None


# --------------------------------------------------------------------------- #
# 符号提取
# --------------------------------------------------------------------------- #
MODULE_SOURCE = '''import os
from . import sibling
from ..core import base as core_base


class Outer:
    """外层类。"""

    def method(self, a, b=1):
        return a

    @staticmethod
    def static_method():
        return 1


def top_level(x):
    def nested(y):
        return y
    return nested(x)
'''


def test_extract_symbols_qualnames_and_kinds() -> None:
    parsed = parse_python_source(MODULE_SOURCE)
    table = {symbol.qualname: symbol for symbol in parsed.symbols}
    assert set(table) == {
        "Outer",
        "Outer.method",
        "Outer.static_method",
        "top_level",
        "top_level.nested",
    }
    assert table["Outer"].kind == "class"
    assert table["Outer.method"].kind == "method"
    assert table["Outer.static_method"].kind == "method"
    assert table["top_level"].kind == "function"
    assert table["top_level.nested"].kind == "function"


def test_extract_symbols_parent_links() -> None:
    parsed = parse_python_source(MODULE_SOURCE)
    table = {symbol.qualname: symbol for symbol in parsed.symbols}
    assert table["Outer"].parent is None
    assert table["Outer.method"].parent == "Outer"
    assert table["top_level"].parent is None
    assert table["top_level.nested"].parent == "top_level"


def test_symbols_inside_compound_statements_are_found() -> None:
    """回归：``if TYPE_CHECKING`` 与 ``try/except ImportError`` 分支里的定义不能漏。"""
    source = '''from typing import TYPE_CHECKING

if TYPE_CHECKING:
    class OnlyForTypes:
        pass


try:
    from fast_json import loads
except ImportError:
    def loads(text):
        return text
'''
    parsed = parse_python_source(source)
    qualnames = {symbol.qualname for symbol in parsed.symbols}
    assert qualnames == {"OnlyForTypes", "loads"}


def test_extract_symbols_sorted_by_lineno() -> None:
    parsed = parse_python_source(MODULE_SOURCE)
    linenos = [symbol.lineno for symbol in parsed.symbols]
    assert linenos == sorted(linenos)


def test_symbol_params_include_self_and_defaults() -> None:
    parsed = parse_python_source(MODULE_SOURCE)
    table = {symbol.qualname: symbol for symbol in parsed.symbols}
    assert table["Outer.method"].params == 3  # self, a, b
    assert table["Outer.static_method"].params == 0
    assert table["top_level"].params == 1


def test_symbol_body_lines() -> None:
    parsed = parse_python_source("def f():\n    return 1\n")
    symbol = _symbol(parsed, "f")
    assert symbol.lineno == 1
    assert symbol.end_lineno == 2
    assert symbol.body_lines == 2


def test_decorators_docstring_and_visibility() -> None:
    source = '''class C:
    @property
    def value(self):
        """值。"""
        return 1

    def _hidden(self):
        return 2
'''
    parsed = parse_python_source(source)
    value = _symbol(parsed, "value")
    assert value.decorators == ["property"]
    assert value.has_docstring is True
    assert value.is_public is True
    assert _symbol(parsed, "_hidden").is_public is False
    assert _symbol(parsed, "_hidden").has_docstring is False


def test_class_symbol_reports_zero_complexity() -> None:
    parsed = parse_python_source("class C:\n    if True:\n        x = 1\n")
    symbol = _symbol(parsed, "C")
    assert symbol.branch_count == 0
    assert symbol.nesting_depth == 0
    assert symbol.params == 0
    assert symbol.cyclomatic_complexity == 1


# --------------------------------------------------------------------------- #
# 复杂度与嵌套深度
# --------------------------------------------------------------------------- #
def test_branch_count_counts_all_documented_node_types() -> None:
    source = '''def f(a, b):
    if a and b:
        return 1
    if a or b or a:
        return 2
    assert a
    return [x for x in range(3) if x if x > 1]
'''
    symbol = _symbol(parse_python_source(source), "f")
    # If(1) + BoolOp(1) + If(1) + BoolOp(2) + Assert(1) + 推导式 if(2) = 8
    assert symbol.branch_count == 8
    assert symbol.cyclomatic_complexity == 9


def test_ternary_and_except_count_as_branches() -> None:
    source = '''def f(x):
    try:
        value = 1 if x else 2
    except ValueError:
        value = 3
    return value
'''
    # IfExp(1) + ExceptHandler(1)；try 本身不计
    assert _symbol(parse_python_source(source), "f").branch_count == 2


def test_match_cases_count_as_branches_and_depth() -> None:
    source = '''def f(x):
    match x:
        case 1:
            return 1
        case _:
            return 0
'''
    symbol = _symbol(parse_python_source(source), "f")
    assert symbol.branch_count == 2
    assert symbol.nesting_depth == 1


def test_nested_definitions_do_not_leak_complexity() -> None:
    source = '''def outer():
    def inner():
        if True:
            return 1
        return 2
    return inner()
'''
    parsed = parse_python_source(source)
    assert _symbol(parsed, "outer").branch_count == 0
    assert _symbol(parsed, "inner").branch_count == 1


def test_nesting_depth_counts_control_flow() -> None:
    source = '''def f(x):
    if x:
        for i in x:
            while i:
                pass
    return x
'''
    assert _symbol(parse_python_source(source), "f").nesting_depth == 3


def test_nesting_depth_ignores_nested_definitions() -> None:
    source = '''def outer():
    if True:
        def inner():
            if True:
                if True:
                    return 1
            return 0
        return inner
    return None
'''
    parsed = parse_python_source(source)
    assert _symbol(parsed, "outer").nesting_depth == 1
    assert _symbol(parsed, "inner").nesting_depth == 2


# --------------------------------------------------------------------------- #
# 导入
# --------------------------------------------------------------------------- #
def test_extract_imports_keeps_relative_prefix() -> None:
    parsed = parse_python_source(MODULE_SOURCE)
    assert parsed.imports == [".", "..core", "os"]


def test_extract_imports_deduplicates() -> None:
    source = "import os\nimport os\nfrom os import path\n"
    assert parse_python_source(source).imports == ["os"]


# --------------------------------------------------------------------------- #
# 容错
# --------------------------------------------------------------------------- #
def test_syntax_error_degrades_without_raising() -> None:
    parsed = parse_python_source("def broken(:\n    pass\n")
    assert parsed.parse_error is not None
    assert parsed.parse_error.startswith("line 1:")
    assert parsed.symbols == []
    assert parsed.imports == []
    assert parsed.lines.docstring == 0
    counts = parsed.lines
    assert counts.total == counts.code + counts.comment + counts.docstring + counts.blank


def test_extract_symbols_on_bare_module() -> None:
    import ast

    assert extract_symbols(ast.parse("x = 1\n")) == []
    assert extract_imports(ast.parse("x = 1\n")) == []
