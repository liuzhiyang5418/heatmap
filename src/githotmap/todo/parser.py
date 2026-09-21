"""TODO 标记解析核心（正则 + 词法定位）。

本模块是 TODO Detection Module 的关键：用**正则**从源码注释中匹配技术债标记，
并提取标记之后的任务描述。

设计取舍（与 ``scanner/parser.py`` 一致，优先用词法事实而非行首正则）：

- 用标准库 ``tokenize`` 找出**真正的注释行**（``#`` 注释），
  从而把字符串字面量里的 ``TODO`` 排除（例如 ``msg = "TODO: ..."`` 不会被误判）；
- 用标准库 ``ast`` 定位**文档字符串**覆盖的行，docstring 中的标记同样会被提取；
- 只有命中注释/docstring 的行才会交给正则匹配，保证准确；
- 任何词法/语法失败都**降级**而非抛异常：单文件出错绝不影响整次检测。
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from typing import Iterator

from githotmap.todo.models import TodoItem, TodoKind

#: 技术债标记正则：\b 保证单词边界（避免误匹配 "TODOING"），忽略大小写识别 todo/TODO。
_MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

#: 标记名称（大写）-> 枚举实例，避免反复构造并让 mypy 收窄类型。
_KIND_BY_NAME: dict[str, TodoKind] = {kind.value: kind for kind in TodoKind}

#: 描述前导分隔符（冒号/横杠/星号/空白），提取 description 时去掉。
_DESC_LEAD_RE = re.compile(r"^[\s:：\-*]*")


def _comment_rows(source: str) -> set[int]:
    """返回被 ``#`` 注释覆盖的行号集合（1 起）。

    使用 ``tokenize`` 的 COMMENT token 精确定位，避免把字符串里的井号当注释。
    若词法解析失败（源码语法错误等），退化为「任何含 ``#`` 的行」宽松判断，
    保证不会因词法失败而漏检。
    """
    rows: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                rows.update(range(token.start[0], token.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "#" in line:
                rows.add(lineno)
    return rows


def _docstring_rows(source: str) -> set[int]:
    """返回被文档字符串（模块/类/函数的 docstring）覆盖的行号集合（1 起）。"""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()  # 无法解析时按无 docstring 处理，仍能提取 # 注释

    rows: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr):
            continue
        value = first.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        start = value.lineno
        end = value.end_lineno if value.end_lineno is not None else start
        rows.update(range(start, end + 1))
    return rows


def _extract_description(line: str, match: re.Match[str]) -> str:
    """提取标记之后的描述文字（去掉冒号/横杠/星号与多余空格，并截断过长内容）。"""
    after = line[match.end():]
    return _DESC_LEAD_RE.sub("", after).strip()[:120]


def iter_todos(path: str, source: str) -> Iterator[TodoItem]:
    """逐行扫描源码，产出每条技术债注释（按 ``(lineno, column)`` 升序）。

    参数:
        path  : §4.1 规范的文件路径（供输出携带，供 M4/M5 join）。
        source: 文件源码文本。

    返回:
        技术债条目迭代器，已按行号与列号自然升序（确定性要求）。
    """
    comment_rows = _comment_rows(source)
    docstring_rows = _docstring_rows(source)
    target_rows = comment_rows | docstring_rows

    for lineno, line in enumerate(source.splitlines(), start=1):
        if lineno not in target_rows:
            continue  # 只处理注释/docstring 行，字符串字面量里的 TODO 自然被排除
        for match in _MARKER_RE.finditer(line):
            yield TodoItem(
                path=path,
                kind=_KIND_BY_NAME[match.group(1).upper()],
                lineno=lineno,
                column=match.start() + 1,  # 行内 1 起列号
                text=line.strip(),
                description=_extract_description(line, match),
            )
