"""TODO Detection Module 的门面（消费 M2 的扫描结果）。

关键约束（见 ``docs/scanner-interface.md`` §7.1）：

- 用 ``scan.paths()`` 作为输入面，**不要自行 ``os.walk``**，否则排除规则与全局不一致；
- 读取源码使用 ``errors="replace"`` 降级，单文件出错不影响整体检测；
- 输出路径与扫描器保持一致（§4.1 路径规范），并在 ``TodoScan.path_base`` 记录基准目录。
"""

from __future__ import annotations

from pathlib import Path

from githotmap.scanner import RepositoryScan
from githotmap.todo.models import TodoScan
from githotmap.todo.parser import iter_todos


class TodoDetector:
    """M3 门面：接收 M2 的 :class:`RepositoryScan`，产出结构化 TODO 列表。"""

    name: str = "todo-detector"

    def detect(self, scan: RepositoryScan) -> TodoScan:
        """对扫描结果中的每个文件提取技术债标记。

        参数:
            scan: M2 的扫描结果（含已排序、已排除噪声的文件清单）。

        返回:
            :class:`TodoScan`，条目已按 ``(path, lineno, column)`` 升序排序。
        """
        todos = []
        for path in scan.paths():
            # 用扫描器的基准目录拼接出真实文件路径后读取源码。
            source = (Path(scan.root) / path).read_text(encoding="utf-8", errors="replace")
            todos.extend(iter_todos(path, source))

        # 确定性排序（接口文档 §4.2），保证同样输入得到逐字节相同输出。
        todos.sort(key=lambda t: (t.path, t.lineno, t.column))
        return TodoScan(path_base=scan.path_base, todos=todos)
