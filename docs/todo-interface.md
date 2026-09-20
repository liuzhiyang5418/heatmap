# TODO Detection Module 接口文档

| 项目 | 内容 |
|------|------|
| 模块 | TODO Detection Module（技术债标记检测） |
| 负责人 | Member 3 |
| 对应课程分工 | 需求分析中的「正则解析、技术债信息提取」 |
| 代码位置 | `src/githotmap/todo/` |
| 文档状态 | v0.1（Sprint 1 初稿，待 M4/M5/M6 会签） |
| 适用版本 | githotmap 0.1.0 |

---

## 1. 文档目的

定义 **TODO Detection Module 对外暴露的接口与数据结构**，作为以下模块之间的**书面契约**：

- **M2 (Repository Scanner)** —— 本模块的**输入来源**（消费 `scan.paths()`）；
- **M4 (Git History Analyzer)** —— 与本模块用同一套路径规范做**字典 join**；
- **M5 (Debt Score Engine)** —— 消费本模块的 TODO 计数，作为「显式技术债」信号；
- **M6 (Flask Dashboard)** —— 消费可直接 JSON 序列化的结果。

**约定**：任何一方修改本文档中带「契约」标记的内容，必须同步通知其余成员并更新变更记录。

---

## 2. 模块职责与边界

### 2.1 本模块做什么

从仓库源码的**注释**中提取显式技术债标记：

1. **标记识别**：用正则匹配 `TODO` / `FIXME` / `HACK` / `XXX`；
2. **词法定位**：用标准库 `tokenize` 区分「真正的注释」与「字符串字面量」，
   避免把 `msg = "TODO: ..."` 里的 TODO 误判为技术债；
3. **文档字符串**：用 `ast` 定位模块/类/函数的 docstring，其中的标记同样被提取；
4. **信息提取**：除标记类型、行号、列号外，还提取标记之后的**任务描述**。

### 2.2 本模块**不做**什么（边界）

| 不做的事 | 归属 |
|----------|------|
| 文件发现、目录剪枝、排除规则 | M2 |
| 读取 Git 历史、提交数、churn | M4 |
| 计算技术债分数、风险等级、排序 | M5 |
| 网页/图表展示 | M6 |

---

## 3. 数据流与接口关系

```
   M2 Repository Scan (scan.paths()) ──► M3 Todo Detection ──► M5 / M6
          (文件清单)                      (技术债列表)        (评分/展示)
```

**关键约束**：本模块的输出路径必须能用 §4 的路径规范与 M2 的结果做**字典 join**，
不允许出现路径形态不一致。

---

## 4. 全局共享契约

### 4.1 路径规范【契约】

> 所有对外文件路径一律为「相对于 Git 工作区根目录」的 POSIX 风格路径（正斜杠），
> 不带 `./` 前缀。基准目录与 M2 一致（即 `RepositoryScan.path_base`）。

本模块把实际使用的基准目录写入 `TodoScan.path_base`，便于排查。

### 4.2 确定性【契约】

同样的输入必须产生**逐字节相同**的输出（可复现性）：

- 条目按 `(path, lineno, column)` **升序**排序（`sorted`，不做本地化排序）；
- 不做并发/多线程乱序聚合。

### 4.3 编码与容错

- 读取源码使用 `encoding="utf-8", errors="replace"`，解码失败不抛异常；
- 单文件词法/语法错误**绝不影响整体检测**，只跳过该文件无法可靠识别的部分；
- 判定为注释行使用 `tokenize` 的 `COMMENT` token；docstring 行使用 `ast`。

### 4.4 类型与序列化

- 所有对外数据结构均为 `dataclass(slots=True)` 并实现 `to_dict()`；
- `to_dict()` 返回值只含 JSON 原生类型（`str/int/float/bool/None/list/dict`）；
- 枚举字段在 `to_dict()` 中序列化为其 `str` 值。

---

## 5. 数据结构

### 5.1 `TodoKind` —— 标记类型（枚举）

| 值 | 说明 |
|----|------|
| `TODO` | 待办事项 |
| `FIXME` | 需修复的缺陷 |
| `HACK` | 临时/应急做法，需重构 |
| `XXX` | 有隐患或不规范之处 |

### 5.2 `TodoItem` —— 单条技术债注释

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | §4.1 规范的文件路径 |
| `kind` | `str` | 标记类型（`TodoKind` 的 `str` 值） |
| `lineno` | `int` | 所在行号（1 起） |
| `column` | `int` | 标记在行内的起始列（1 起） |
| `text` | `str` | 该行完整文本（上下文） |
| `description` | `str` | 标记之后的任务描述（技术债信息提取） |

### 5.3 `TodoScan` —— 顶层结果

| 字段 | 类型 | 说明 |
|------|------|------|
| `path_base` | `str` | 实际使用的路径基准目录（与 M2 一致） |
| `todos` | `list[TodoItem]` | 全部技术债条目，按 `(path, lineno, column)` 升序 |

---

## 6. 公共 API

```python
from githotmap.todo import (
    TodoDetector,       # 门面类
    TodoItem,           # 单条技术债
    TodoKind,           # 标记类型枚举
    TodoScan,           # 顶层结果
    iter_todos,         # 单文件正则解析迭代器
)
```

### 6.1 `TodoDetector`

```python
class TodoDetector:
    name: str = "todo-detector"

    def detect(self, scan: RepositoryScan) -> TodoScan:
        """接收 M2 的 RepositoryScan，返回结构化 TODO 列表。"""
```

### 6.2 `iter_todos`

```python
def iter_todos(path: str, source: str) -> Iterator[TodoItem]:
    """逐行扫描单份源码，产出技术债条目（已按行列升序）。"""
```

---

## 7. 下游模块接入约定

### 7.1 给 M5（Debt Score Engine）

可直接消费的数值特征：

| 特征 | 来源 | 用途 |
|------|------|------|
| `todos` 总数 | `TodoScan` | 显式技术债计数 |
| 各类 `kind` 计数 | 同上 | 技术债构成（TODO/FIXME/HACK/XXX） |
| `description` 非空比例 | 同上 | 信息完整度 |

> **权重与归一化归 M5**。本模块只给原始事实，不做任何 0–1 归一化。

### 7.2 给 M6（Flask Dashboard）

```python
from githotmap.scanner import scan_repository
from githotmap.todo import TodoDetector

scan = scan_repository(repo_path)
return jsonify(TodoDetector().detect(scan).to_dict())   # 已是 JSON 原生类型
```

- `todos` 建议在 UI 上按 `path` 分组展示，突出「技术债密集文件」；
- 与 M2 的 `FileStructure` 结合，可展示每文件的 TODO 密度。

---

## 8. 实现状态

| 项 | 状态 |
|----|------|
| 正则标记识别（TODO/FIXME/HACK/XXX） | ✅ 已实现 |
| tokenize 注释行定位（排除字符串内假标记） | ✅ 已实现 |
| docstring 标记提取（ast 定位） | ✅ 已实现 |
| 任务描述提取（信息提取） | ✅ 已实现 |
| 确定性排序 | ✅ 已实现 |
| 单元测试 | ✅ 已实现 |
| `ruff check`（todo 目录） | ✅ 通过 |
| `mypy --strict`（todo 目录） | ✅ 通过 |

---

## 9. 扩展点与后续 Sprint

- **Sprint 2**：支持更多语言（如 JS/Go）的注释识别；接入增量扫描（基于 M2 的 `sha256` 跳过未变文件）。
- **Sprint 3**：接入 `core/pipeline.py`，把 `TodoScan` 作为评分引擎的输入之一。

---

## 10. 变更记录

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| v0.1 | Sprint 1 | 初稿：定义路径规范、3 个数据结构、公共 API、下游接入约定 | Member 3 |
