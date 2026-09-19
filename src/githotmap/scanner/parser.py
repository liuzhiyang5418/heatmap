"""Python 源码结构解析层：基于标准库 ``ast`` 与 ``tokenize``。

产物是**语言无关契约**（:class:`~githotmap.scanner.models.FileStructure`）所需的三部分事实：

1. 符号树 —— 类 / 函数 / 方法，含行号区间、装饰器、文档字符串、圈复杂度近似、嵌套深度；
2. 导入清单 —— ``import`` 与 ``from ... import`` 的模块名（相对导入保留前导点）；
3. 行数构成 —— 代码 / 注释 / 文档字符串 / 空行，四项之和严格等于总行数。

设计取舍：

- 行数分类以 ``tokenize`` 的词法事实为准（而不是行首正则），因此 ``x = "# 不是注释"``
  这类字符串内井号不会被误判为注释；
- 文档字符串的行号来自 ``ast`` 的 ``Constant`` 节点区间，因此多行 docstring 覆盖的行
  （含其中的空行）统一计入 ``docstring``；
- 任何解析失败都**降级**而非抛异常：单文件出错绝不影响整次扫描。
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, field
from typing import Iterator

from githotmap.scanner.models import LineCounts, SymbolInfo, SymbolKind

#: 会「截断」复杂度归属的节点：这些节点内部的分支算给它们自己的符号，不累加到外层。
_DEF_NODES: tuple[type[ast.AST], ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)

#: 计入 ``branch_count`` 的单节点分支（``elif`` 在 AST 中是嵌套 ``If``，故只计 1 次）。
_BRANCH_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.Assert,
    ast.match_case,
)

#: 计入 ``nesting_depth`` 的复合语句。
_NESTING_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)

#: 不产生「代码行」的 token 类型。
_SKIP_TOKENS: frozenset[int] = frozenset(
    {
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)

#: 三类带装饰器的定义节点。
_DefNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


@dataclass(slots=True)
class ParsedSource:
    """Python 源码的解析产物，供 scanner 组装 :class:`FileStructure`。"""

    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    lines: LineCounts = field(default_factory=LineCounts)
    parse_error: str | None = None


# --------------------------------------------------------------------------- #
# 符号提取
# --------------------------------------------------------------------------- #
def _descend(node: ast.AST) -> Iterator[ast.AST]:
    """深度优先产出节点，遇到嵌套的函数/类/lambda 定义即停止下探。"""
    if isinstance(node, _DEF_NODES):
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _descend(child)


def _function_body_nodes(node: _DefNode) -> Iterator[ast.AST]:
    """产出函数体内的全部节点（不含形参、装饰器与嵌套定义）。"""
    for statement in node.body:
        yield from _descend(statement)


def _param_count(args: ast.arguments) -> int:
    """形参个数（含 ``self``/``cls``、``*args``、``**kwargs`` 与仅关键字参数）。"""
    total = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.vararg is not None:
        total += 1
    if args.kwarg is not None:
        total += 1
    return total


def _branch_count(node: _DefNode) -> int:
    """函数体内分支点的原始计数（圈复杂度近似，口径见接口文档 §5.2）。"""
    total = 0
    for child in _function_body_nodes(node):
        if isinstance(child, _BRANCH_NODES):
            total += 1
        elif isinstance(child, ast.BoolOp):
            # a and b and c -> 2 个分支点
            total += max(len(child.values) - 1, 0)
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            # 推导式按 if 子句个数计分支。
            # 此处用字面量元组而非模块级常量，否则 mypy 无法收窄类型、看不到 .generators。
            total += sum(len(generator.ifs) for generator in child.generators)
    return total


def _nesting_depth(node: _DefNode) -> int:
    """函数体内控制流语句的最大嵌套深度。"""

    def level_of(candidate: ast.AST, level: int) -> int:
        return level + 1 if isinstance(candidate, _NESTING_NODES) else level

    def depth(current: ast.AST, level: int) -> int:
        best = level
        for child in ast.iter_child_nodes(current):
            if isinstance(child, _DEF_NODES):
                continue
            best = max(best, depth(child, level_of(child, level)))
        return best

    best = 0
    for statement in node.body:
        if isinstance(statement, _DEF_NODES):
            continue
        best = max(best, depth(statement, level_of(statement, 0)))
    return best


def _build_symbol(
    node: _DefNode, qualname: str, parent: str | None, kind: SymbolKind
) -> SymbolInfo:
    """把一个 AST 定义节点转换为 :class:`SymbolInfo`。"""
    if isinstance(node, ast.ClassDef):
        # 类本身不计复杂度，复杂度归属到其中的函数/方法。
        params = 0
        branches = 0
        depth = 0
    else:
        params = _param_count(node.args)
        branches = _branch_count(node)
        depth = _nesting_depth(node)

    end_lineno = node.end_lineno if node.end_lineno is not None else node.lineno
    return SymbolInfo(
        name=node.name,
        qualname=qualname,
        kind=kind.value,
        parent=parent,
        lineno=node.lineno,
        end_lineno=end_lineno,
        decorators=[ast.unparse(decorator) for decorator in node.decorator_list],
        has_docstring=ast.get_docstring(node, clean=False) is not None,
        is_public=not node.name.startswith("_"),
        params=params,
        branch_count=branches,
        nesting_depth=depth,
    )


def extract_symbols(tree: ast.Module) -> list[SymbolInfo]:
    """提取全部类/函数/方法符号，按 ``(lineno, name)`` 升序返回。

    嵌套定义同样会产出符号，其 ``parent`` 指向外层符号的 ``qualname``；
    直接位于类体内的函数 ``kind`` 为 ``method``，其余为 ``function``。

    除了直接子节点，还会下探到 ``if``/``try``/``with`` 等复合语句内部——
    否则 ``if TYPE_CHECKING:`` 与 ``try/except ImportError`` 兼容分支中的定义会被漏掉。
    """
    symbols: list[SymbolInfo] = []

    def visit(node: ast.AST, prefix: str, parent: str | None, in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                qualname = f"{prefix}{child.name}"
                symbols.append(_build_symbol(child, qualname, parent, SymbolKind.CLASS))
                visit(child, f"{qualname}.", qualname, True)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                kind = SymbolKind.METHOD if in_class else SymbolKind.FUNCTION
                symbols.append(_build_symbol(child, qualname, parent, kind))
                visit(child, f"{qualname}.", qualname, False)
            else:
                visit(child, prefix, parent, in_class)

    visit(tree, "", None, False)
    symbols.sort(key=lambda symbol: (symbol.lineno, symbol.name))
    return symbols


def extract_imports(tree: ast.Module) -> list[str]:
    """提取被导入的模块名，去重后排序；相对导入保留前导点（如 ``..core``）。"""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * (node.level or 0)
            if node.module is not None:
                modules.add(f"{prefix}{node.module}")
            elif prefix:
                modules.add(prefix)
    return sorted(modules)


# --------------------------------------------------------------------------- #
# 行数统计
# --------------------------------------------------------------------------- #
def docstring_rows(tree: ast.AST) -> set[int]:
    """返回被文档字符串覆盖的全部行号（1 起，含多行区间）。"""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    rows: set[int] = set()
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


def count_lines_plain(source: str) -> LineCounts:
    """无需解析的粗粒度行数统计：只区分空行与代码行。

    用于快速模式、非 Python 文件，以及 ``tokenize`` 也失败时的兜底。
    此时 ``comment`` 与 ``docstring`` 恒为 0。
    """
    lines = source.splitlines()
    total = len(lines)
    blank = sum(1 for line in lines if not line.strip())
    return LineCounts(total=total, code=total - blank, blank=blank)


def classify_lines(source: str, docstring_line_rows: set[int]) -> LineCounts:
    """把每一行分类为 代码/注释/文档字符串/空白（四类互斥，和等于总行数）。

    优先级：``docstring`` > ``code``（多行字符串内容行与含行尾注释的代码行均计入
    ``code``）> ``comment``（整行注释）> ``blank``。
    """
    lines = source.splitlines()
    total = len(lines)
    if total == 0:
        return LineCounts()

    comment_rows: set[int] = set()
    string_rows: set[int] = set()
    code_rows: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            kind = token.type
            if kind == tokenize.COMMENT:
                comment_rows.update(range(token.start[0], token.end[0] + 1))
            elif kind == tokenize.STRING:
                string_rows.update(range(token.start[0], token.end[0] + 1))
                if token.start[0] not in docstring_line_rows:
                    code_rows.add(token.start[0])
            elif kind in _SKIP_TOKENS:
                continue
            else:
                code_rows.add(token.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        # 词法层面都无法处理时退回粗粒度统计，仍保证不变量成立。
        return count_lines_plain(source)

    code = comment = docstring = blank = 0
    for row in range(1, total + 1):
        if row in docstring_line_rows:
            docstring += 1
        elif row in string_rows or row in code_rows:
            code += 1
        elif row in comment_rows:
            comment += 1
        elif not lines[row - 1].strip():
            blank += 1
        else:
            code += 1

    return LineCounts(
        total=total, code=code, comment=comment, docstring=docstring, blank=blank
    )


# --------------------------------------------------------------------------- #
# 顶层入口
# --------------------------------------------------------------------------- #
def _describe_error(exc: BaseException) -> str:
    """把解析异常整理成人类可读的一行描述。"""
    if isinstance(exc, SyntaxError):
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        return f"{location}: {exc.msg}"
    return f"{type(exc).__name__}: {exc}"


def parse_python_source(source: str) -> ParsedSource:
    """解析 Python 源码；语法错误时降级为「行数统计 + 空符号」，**不抛异常**。

    语法错误路径下无法可靠取得文档字符串区间，因此该文件的 ``docstring`` 恒为 0，
    对应行会计入 ``code``。
    """
    if not source.strip():
        return ParsedSource(lines=count_lines_plain(source))

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return ParsedSource(
            lines=classify_lines(source, set()),
            parse_error=_describe_error(exc),
        )

    return ParsedSource(
        symbols=extract_symbols(tree),
        imports=extract_imports(tree),
        lines=classify_lines(source, docstring_rows(tree)),
        parse_error=None,
    )
