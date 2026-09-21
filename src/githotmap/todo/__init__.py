"""TODO Detection Module —— Member 3 负责的模块。

职责：从仓库源码的**注释**中提取显式技术债标记（TODO / FIXME / HACK / XXX），
产出结构化、可 JSON 序列化的技术债列表，供 M5（Debt Score Engine）评分输入
与 M6（Flask Dashboard）展示消费。

与下游模块的边界（见 ``docs/todo-interface.md``）：

- **输入**：消费 M2 (Repository Scanner) 的 ``scan.paths()``，不自行 ``os.walk``；
- **输出**：遵循 §4.1 路径规范（Git 根相对 + POSIX 正斜杠、无 ``./`` 前缀），
  每个 TODO 附带 ``path`` 与 ``lineno``，供 M4/M5 做字典 join；
- **不做**：读取 Git 历史（M4）、计算技术债分数（M5）、做任何展示（M6）。

典型用法::

    from githotmap.scanner import scan_repository
    from githotmap.todo import TodoDetector

    scan = scan_repository(".")            # M2：得到文件清单
    result = TodoDetector().detect(scan)    # M3：提取技术债
    print(result.to_dict())                 # M6 可直接 json.dumps
"""

from __future__ import annotations

from githotmap.todo.detector import TodoDetector
from githotmap.todo.models import TodoItem, TodoKind, TodoScan
from githotmap.todo.parser import iter_todos

__all__ = ["TodoDetector", "TodoItem", "TodoKind", "TodoScan", "iter_todos"]
