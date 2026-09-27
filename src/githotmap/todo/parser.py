"""TODO 标记解析核心（正则 + 词法定位）。

本模块是 TODO Detection Module 的关键：用**正则**从源码注释中匹配技术债标记，
并提取标记之后的任务描述。

设计取舍（与 ``scanner/parser.py`` 一致，优先用词法事实而非行首正则）：

- 用标准库 ``tokenize`` 找出**真正的注释 token**（``#`` 注释），
  直接在注释文本内部进行正则匹配，从而杜绝代码行内字符串（如 ``msg = "TODO"  # 普通注释``）
  造成的假阳性；
- 用标准库 ``ast`` 定位**文档字符串**覆盖的行，仅对属于 docstring 的字符串 token 提取标记；
- 排序与确定性：产出的条目保证按 ``(lineno, column)`` 严格升序；
- 任何词法/语法失败都**降级**而非抛异常：单文件出错绝不影响整次检测。
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator

from githotmap.todo.models import TodoItem, TodoKind

#: 技术债标记正则：\b 保证单词边界（避免误匹配 "TODOING"），忽略大小写识别 todo/TODO。
_MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

#: 标记名称（大写）-> 枚举实例，避免反复构造并让 mypy 收窄类型。
_KIND_BY_NAME: dict[str, TodoKind] = {kind.value: kind for kind in TodoKind}

#: 描述前导分隔符（冒号/横杠/星号/空白），提取 description 时去掉。
_DESC_LEAD_RE = re.compile(r"^[\s:：\-*]*")


def _docstring_rows(source: str) -> set[int]:
    """返回被文档字符串（模块/类/函数的 docstring）覆盖的行号集合（1 起）。"""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()

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


def _extract_description(text: str, match: re.Match[str]) -> str:
    """提取标记之后的描述文字（去掉冒号/横杠/星号与多余空格，并截断过长内容）。"""
    after = text[match.end():]
    desc = _DESC_LEAD_RE.sub("", after).strip()
    # 清理行末尾可能存在的 docstring 闭合引号
    desc = re.sub(r'["\']+$', "", desc).strip()
    return desc[:120]


def _iter_todos_fallback(path: str, source: str) -> list[TodoItem]:
    """tokenize 发生语法/词法错误时的降级逻辑：按行寻找 # 注释部分。"""
    todos: list[TodoItem] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        hash_idx = line.find("#")
        if hash_idx == -1:
            continue
        comment_part = line[hash_idx:]
        for match in _MARKER_RE.finditer(comment_part):
            todos.append(
                TodoItem(
                    path=path,
                    kind=_KIND_BY_NAME[match.group(1).upper()],
                    lineno=lineno,
                    column=hash_idx + match.start() + 1,
                    text=comment_part.strip(),
                    description=_extract_description(comment_part, match),
                )
            )
    return todos


def iter_todos(path: str, source: str) -> Iterator[TodoItem]:
    """逐行扫描源码，产出每条技术债注释（按 ``(lineno, column)`` 升序）。

    参数:
        path  : §4.1 规范的文件路径（供输出携带，供 M4/M5 join）。
        source: 文件源码文本。

    返回:
        技术债条目迭代器，已按行号与列号自然升序（确定性要求）。
    """
    if not source.strip():
        return

    doc_rows = _docstring_rows(source)
    todos: list[TodoItem] = []

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        yield from _iter_todos_fallback(path, source)
        return

    for token in tokens:
        # 1. 普通 # 注释（含行首与行尾注释）
        if token.type == tokenize.COMMENT:
            comment_text = token.string
            start_line, start_col = token.start
            for match in _MARKER_RE.finditer(comment_text):
                todos.append(
                    TodoItem(
                        path=path,
                        kind=_KIND_BY_NAME[match.group(1).upper()],
                        lineno=start_line,
                        column=start_col + match.start() + 1,
                        text=comment_text.strip(),
                        description=_extract_description(comment_text, match),
                    )
                )

        # 2. 属于 docstring 的字符串 token
        elif token.type == tokenize.STRING and token.start[0] in doc_rows:
            doc_lines = token.string.splitlines()
            base_line = token.start[0]
            for i, line_content in enumerate(doc_lines):
                cur_line = base_line + i
                col_offset = token.start[1] if i == 0 else 0
                for match in _MARKER_RE.finditer(line_content):
                    todos.append(
                        TodoItem(
                            path=path,
                            kind=_KIND_BY_NAME[match.group(1).upper()],
                            lineno=cur_line,
                            column=col_offset + match.start() + 1,
                            text=line_content.strip(),
                            description=_extract_description(line_content, match),
                        )
                    )

    # 确定性排序：按 (lineno, column) 升序
    todos.sort(key=lambda t: (t.lineno, t.column))
    yield from todos
