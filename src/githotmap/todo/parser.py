"""TODO 标记解析核心（正则 + 词法定位）。

本模块是 TODO Detection Module 的关键：用**正则**从源码注释中匹配技术债标记，
并提取标记之后的任务描述。

设计取舍（与 ``scanner/parser.py`` 一致，优先用词法事实而非行首正则）：

- 用标准库 ``tokenize`` 找出**真正的注释 token**（``#`` 注释），
  直接在注释文本内部进行正则匹配，从而杜绝代码行内字符串（如 ``msg = "TODO"  # 普通注释``）
  造成的假阳性；
- 用标准库 ``ast`` 定位**文档字符串**覆盖的行，仅对属于 docstring 的字符串 token 提取标记；
- 排序与确定性：产出的条目保证按 ``(lineno, column)`` 严格升序；
- 信息提取：标记之后的文本进一步解析出责任人（``owner``）、关联引用（``ref``）
  与紧急程度（``severity``），供 M5 加权、M6 展示；
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

#: 责任人/引用解析：圆括号、@ 提及、# 编号（均在标记之后的文本中查找）。
_PAREN_RE = re.compile(r"\(([^()]+)\)")
_AT_RE = re.compile(r"@([A-Za-z0-9_][\w.\-]*)")
_HASH_RE = re.compile(r"#(\d+)")

#: 判定圆括号内容是否属于"引用"而非人名：纯数字编号或 PROJ-123 形式的工单号。
_REF_LIKE_RE = re.compile(r"^(#\d+|[A-Za-z][A-Za-z0-9]*-\d+)$")

#: 判定圆括号内容是否属于"责任人"：ASCII 标识符（alice/zhang.san）或 2~10 位中文名。
_NAME_LIKE_RE = re.compile(r"^[A-Za-z][\w.\-]*$|^[一-龥]{2,10}$")

#: 严重等级关键词（大小写不敏感）：命中越靠前的规则等级越高，默认 1。
_SEVERITY_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (
        re.compile(
            r"\b(urgent|asap|critical|blocker|immediately|high[\s-]?priority|p0|p1)\b",
            re.IGNORECASE,
        ),
        3,
    ),
    (
        re.compile(r"\b(important|soon|medium[\s-]?priority|should|p2)\b", re.IGNORECASE),
        2,
    ),
]


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


def _extract_description(after: str) -> str:
    """提取标记之后的描述文字（去掉冒号/横杠/星号与多余空格，并截断过长内容）。"""
    desc = _DESC_LEAD_RE.sub("", after).strip()
    # 清理行末尾可能存在的 docstring 闭合引号
    desc = re.sub(r"['\"]+$", "", desc).strip()
    return desc[:120]


def _extract_meta(after: str) -> tuple[str, str, int]:
    """从标记之后的文本中提取 (owner, ref, severity)。

    解析规则：
    - ``TODO(alice):``  → 圆括号内非工单号内容判为人名 → owner；
    - ``TODO(HEATMAP-45):`` / ``TODO(#123)`` → 圆括号内工单号形态 → ref；
    - ``TODO @alice`` → @ 提及 → owner（仅在前面没解析到时）；
    - ``TODO #123`` → # 编号 → ref（仅在前面没解析到时）；
    - ``urgent/critical`` 等词 → severity 3，``important/should`` → 2，否则 1。
    """
    owner = ""
    ref = ""

    paren = _PAREN_RE.search(after)
    if paren:
        content = paren.group(1).strip()
        if content:
            if _REF_LIKE_RE.match(content):
                ref = content
            elif _NAME_LIKE_RE.match(content):
                owner = content
        # 既不像工单号也不像人名的括号内容（如 "see #123"）直接忽略，避免误判。

    at_match = _AT_RE.search(after)
    if at_match and not owner:
        owner = at_match.group(1)

    hash_match = _HASH_RE.search(after)
    if hash_match and not ref:
        ref = f"#{hash_match.group(1)}"

    severity = 1
    for pattern, level in _SEVERITY_PATTERNS:
        if level > severity and pattern.search(after):
            severity = level

    return owner, ref, severity


def _make_item(path: str, match: re.Match[str], lineno: int, column: int, text: str) -> TodoItem:
    """按统一规则把一次正则匹配构造成 :class:`TodoItem`（唯一的构造点）。"""
    after = text[match.end():]
    owner, ref, severity = _extract_meta(after)
    return TodoItem(
        path=path,
        kind=_KIND_BY_NAME[match.group(1).upper()],
        lineno=lineno,
        column=column,
        text=text.strip(),
        description=_extract_description(after),
        owner=owner,
        ref=ref,
        severity=severity,
    )


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
                _make_item(path, match, lineno, hash_idx + match.start() + 1, comment_part)
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
                    _make_item(
                        path, match, start_line, start_col + match.start() + 1, comment_text
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
                        _make_item(
                            path, match, cur_line, col_offset + match.start() + 1, line_content
                        )
                    )

    # 确定性排序：按 (lineno, column) 升序
    todos.sort(key=lambda t: (t.lineno, t.column))
    yield from todos
