"""TODO Detection Module 的门面（消费 M2 的扫描结果）。

关键约束（见 ``docs/scanner-interface.md`` §7.1 与 ``docs/todo-interface.md`` §4.3/§4.5）：

- 用 ``scan.paths()`` 作为输入面，**不要自行 ``os.walk``**，否则排除规则与全局不一致；
- 带有 ``symlink`` / ``too-large`` / ``not-text`` 限制标记的条目直接跳过——
  扫描器有意不提供这些文件的内容，跟随符号链接或全量读取超大文件既危险又浪费（M3-3/M3-6）；
- 单文件读取失败（``OSError``：不存在/无权限/是目录）**跳过该文件而非中断整次检测**
  （M3-2），解码异常由 ``errors="replace"`` 兜底；
- **NFR-2 可审计性**：任何跳过都**不静默**——每次降级都会向 ``TodoScan.degradations``
  追加一条带原因码的记录（见 :class:`~githotmap.todo.models.TodoDegradation`）；
- 输出路径与扫描器保持一致（§4.1 路径规范），并在 ``TodoScan.path_base`` 记录基准目录。
"""

from __future__ import annotations

from pathlib import Path

from githotmap.scanner import Limitation, RepositoryScan
from githotmap.todo.models import TodoDegradation, TodoItem, TodoScan
from githotmap.todo.parser import iter_todos

#: 带这些限制标记的文件不参与检测：
#: symlink（符号链接，可能指向仓库外或失效目标）、too-large（超大文件）、not-text（二进制）。
_SKIP_LIMITATIONS: frozenset[str] = frozenset(
    {
        Limitation.SYMLINK.value,
        Limitation.TOO_LARGE.value,
        Limitation.NOT_TEXT.value,
    }
)


class TodoDetector:
    """M3 门面：接收 M2 的 :class:`RepositoryScan`，产出结构化 TODO 列表。"""

    name: str = "todo-detector"

    def detect(self, scan: RepositoryScan) -> TodoScan:
        """对扫描结果中的每个文件提取技术债标记。

        参数:
            scan: M2 的扫描结果（含已排序、已排除噪声的文件清单）。

        返回:
            :class:`TodoScan`，条目与降级记录均已按 ``(path, ...)`` 升序排序。
        """
        by_path = scan.by_path()
        todos: list[TodoItem] = []
        degradations: list[TodoDegradation] = []
        for path in scan.paths():
            # M3-3/M3-6：跳过扫描器已标记为符号链接 / 超大文件 / 二进制的条目，
            # 并按 NFR-2 记录原因码。按 limitations 列表顺序取首个命中，
            # 保证同一输入得到相同记录（确定性）。
            structure = by_path.get(path)
            skip_code: str | None = None
            if structure is not None:
                for limitation in structure.limitations:
                    if limitation in _SKIP_LIMITATIONS:
                        skip_code = limitation
                        break
            if skip_code is not None:
                degradations.append(
                    TodoDegradation(
                        code=skip_code,
                        path=path,
                        summary=f"skipped: file marked {skip_code} by scanner",
                    )
                )
                continue

            # scan.paths() 是相对 path_base（Git 工作区根）的，不能拿 scan.root 拼接：
            # 当扫描的是仓库子目录时 root != path_base，会拼出 …/子目录/子目录/… 的不存在路径。
            # 见 docs/scanner-interface.md §4.1 与 §7.1。
            try:
                source = (Path(scan.path_base) / path).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError as exc:
                # M3-2：单个文件读取失败（FileNotFoundError/PermissionError/
                # IsADirectoryError 等）时跳过，绝不中断整次检测——
                # 与接口文档 §4.3「单文件出错绝不影响整体检测」的容错承诺一致。
                # NFR-2：跳过必须留痕，summary 只用异常类名（不含路径消息）以保可复现。
                degradations.append(
                    TodoDegradation(
                        code=Limitation.UNREADABLE.value,
                        path=path,
                        summary=f"read failed: {type(exc).__name__}",
                    )
                )
                continue
            todos.extend(iter_todos(path, source))

        # 确定性排序（接口文档 §4.2），保证同样输入得到逐字节相同输出。
        todos.sort(key=lambda t: (t.path, t.lineno, t.column))
        degradations.sort(key=lambda d: (d.path, d.code))
        return TodoScan(
            path_base=scan.path_base, todos=todos, degradations=degradations
        )
