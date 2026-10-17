"""TODO Detection Module 的领域模型（契约层）。

与 ``core/models.py`` 与 ``scanner/models.py`` 的约定保持一致：

- 只依赖标准库，不反向依赖任何上层模块；
- 每个模型均为 ``dataclass(slots=True)`` 且实现 ``to_dict()``，
  返回值只含 JSON 原生类型，M6 可直接 ``json.dumps``；
- 枚举字段以 ``str`` 值出现在数据结构字段中（字段用字符串、内部用枚举）。

路径规范【契约】：对外 ``path`` 一律为「Git 工作区根相对 + POSIX 正斜杠」，
不带 ``./`` 前缀，详见 ``docs/todo-interface.md`` §4.1。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TodoKind(str, Enum):
    """技术债标记类型。

    不同标记代表不同类型的技术债，权重由 M5 决定：
    - TODO  ：待办事项
    - FIXME ：需要修复的缺陷
    - HACK  ：临时/应急做法，需要重构
    - XXX   ：有隐患或不规范之处
    """

    TODO = "TODO"
    FIXME = "FIXME"
    HACK = "HACK"
    XXX = "XXX"


@dataclass(slots=True)
class TodoItem:
    """单条技术债注释。

    字段说明：
    - ``path``    ：§4.1 规范的文件路径，供 M4/M5 做字典 join；
    - ``kind``    ：标记类型（枚举，``to_dict()`` 时序列化为其 ``str`` 值）；
    - ``lineno``  ：所在行号（1 起）；
    - ``column``  ：标记在行内的起始列（1 起）；
    - ``text``    ：该行完整文本（作上下文，便于人工查看）；
    - ``description``：标记之后的任务描述（技术债信息提取的结果）。
    """

    path: str
    kind: TodoKind
    lineno: int
    column: int
    text: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转成只含 JSON 原生类型的字典，供 M6 ``json.dumps``。"""
        return {
            "path": self.path,
            "kind": self.kind.value,          # 枚举 -> str
            "lineno": self.lineno,
            "column": self.column,
            "text": self.text,
            "description": self.description,
        }


@dataclass(slots=True)
class TodoScan:
    """一次检测的顶层产出（对应 M2 的 ``RepositoryScan``）。"""

    #: 实际使用的路径基准目录（来自扫描结果，便于排查）。
    path_base: str = ""
    #: 全部技术债条目，已按 ``(path, lineno, column)`` 升序排序（确定性要求）。
    todos: list[TodoItem] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """检出的技术债标记总数。"""
        return len(self.todos)

    def paths(self) -> list[str]:
        """返回所有包含技术债的文件路径列表（升序、去重）。"""
        seen: set[str] = set()
        res: list[str] = []
        for t in self.todos:
            if t.path not in seen:
                seen.add(t.path)
                res.append(t.path)
        return res

    def by_path(self) -> dict[str, list[TodoItem]]:
        """按文件路径建立技术债索引，供 M4/M5 做字典 join。

        返回:
            {文件路径: 该文件内的 TodoItem 列表}（条目内部保持行号升序）。
        """
        mapping: dict[str, list[TodoItem]] = defaultdict(list)
        for t in self.todos:
            mapping[t.path].append(t)
        return dict(mapping)

    def count_by_kind(self) -> dict[str, int]:
        """统计各类标记的数量（如 {'TODO': 12, 'FIXME': 3, 'HACK': 1, 'XXX': 0}）。

        返回的字典包含全部 TodoKind 枚举键，供 M6 图表直接消费，无需额外判空。
        """
        counts: dict[str, int] = {k.value: 0 for k in TodoKind}
        for t in self.todos:
            counts[t.kind.value] += 1
        return counts

    def count_by_path(self) -> dict[str, int]:
        """按文件统计技术债数量索引，供 M5 评分引擎快速获取文件级技术债信号。

        返回:
            {文件路径: 技术债总数}。
        """
        return {path: len(items) for path, items in self.by_path().items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_base": self.path_base,
            "total_count": self.total_count,
            "counts_by_kind": self.count_by_kind(),
            "todos": [t.to_dict() for t in self.todos],
        }
