# Repository Scanner 接口文档

| 项目 | 内容 |
|------|------|
| 模块 | Repository Scanner（仓库扫描器） |
| 负责人 | Member 2 |
| 对应课程分工 | 需求分析中的「Python 文件扫描、代码结构解析」 |
| 代码位置 | `src/githotmap/scanner/` |
| 文档状态 | v0.1（Sprint 1 初稿，待 M3/M4/M5/M6 会签） |
| 适用版本 | githotmap 0.1.0 |

---

## 1. 文档目的

本文档定义 **Repository Scanner 对外暴露的接口与数据结构**，作为以下模块之间的**书面契约**：

- Member 3（TODO Detection Module）—— 需要扫描器的文件清单与文件内容访问方式
- Member 4（Git History Analyzer）—— 需要与历史数据**逐路径对齐**
- Member 5（Debt Score Engine）—— 需要结构化数值特征作为评分输入
- Member 6（Flask Dashboard + Testing）—— 需要可直接 JSON 序列化的结果

**约定：任何一方修改本文档中带「契约」标记的内容，必须同步通知其余成员并更新本文档的变更记录。**

---

## 2. 模块职责与边界

### 2.1 本模块做什么

扫描仓库**工作区**（worktree）当前状态，产出**静态结构事实**：

1. **文件发现**：按后缀与排除规则遍历目录，给出确定性排序的候选文件清单；
2. **结构解析**：对 Python 文件用标准库 `ast` 解析出类/函数/方法符号、导入、行数构成；
3. **规模度量**：文件字节数、总行/代码行/注释行/文档字符串行/空行、内容哈希；
4. **可审计性**：记录被排除的内容与解析失败原因，供 M6 展示扫描覆盖率。

### 2.2 本模块**不做**什么（边界，避免职责重叠）

| 不做的事 | 归属 |
|----------|------|
| 读取 Git 历史、提交数、churn、贡献者 | Member 4 |
| 提取 TODO/FIXME/HACK 等技术债注释 | Member 3 |
| 计算技术债分数、风险等级、排序 | Member 5 |
| 网页/图表展示 | Member 6 |
| 判断某文件"是否值得重构" | Member 5 |

> 注意：扫描器**不读取 Git 历史**，只读工作区文件系统。工作区状态与 HEAD 提交状态可能不一致（未提交的改动会被计入），这是**有意设计**——具体取舍见 §9。

---

## 3. 数据流与接口关系

```
                      ┌─────────────────────────────┐
   仓库工作区 ───────►│  Repository Scanner (M2)     │
                      │  walker → parser → scanner   │
                      └──────────────┬──────────────┘
                                     │ RepositoryScan
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
      ┌───────────────┐     ┌────────────────┐    ┌──────────────────┐
      │ M3 TODO       │     │ M4 Git History │    │ M5 Debt Score    │
      │ Detection     │     │ Analyzer       │    │ Engine           │
      │ 消费: 文件清单 │     │ 消费: 路径规范  │    │ 消费: 数值特征    │
      │ 产出: TODO 列表│     │ 产出: 历史指标  │    │ 产出: 分数/等级   │
      └───────┬───────┘     └────────┬───────┘    └────────┬─────────┘
              │                      │                      │
              └──────────────────────┼──────────────────────┘
                                     ▼
                          ┌────────────────────┐
                          │ M6 Flask Dashboard │
                          └────────────────────┘
```

**关键约束**：M3 与 M4 的输出都必须能用 §4.1 的路径规范与扫描器结果做**字典 join**，不允许出现路径形态不一致。

---

## 4. 全局共享契约

### 4.1 路径规范【契约 · 最重要】

> **所有跨模块传递的文件路径，一律为「相对于 Git 工作区根目录」的 POSIX 风格路径（正斜杠），不带 `./` 前缀。**

| 规则 | 说明 |
|------|------|
| 基准目录 | Git 工作区根（`git rev-parse --show-toplevel` 的结果），**不是** 扫描时传入的目录 |
| 分隔符 | 正斜杠 `/`，即使在 Windows 上 |
| 前缀 | 无 `./`、无前导 `/` |
| 大小写 | 保留文件系统原始大小写 |
| 示例 | `src/githotmap/core/git.py` ✅ ／ `./src\githotmap\core\git.py` ❌ |

**为什么钉死这一条**：`git log --numstat` 输出的就是仓库根相对路径。若扫描器按传入目录相对化，当用户传入仓库子目录时，M2 与 M4 的键会**静默错配**，所有文件的历史指标退化为 0。扫描器默认开启 `respect_git_root=True` 来消除该风险。

- 不含 Git 仓库时（普通文件夹），基准目录回退为传入的扫描根目录。
- 扫描器会把实际使用的基准目录写入 `RepositoryScan.path_base`，便于排查。

> ⚠️ **非 ASCII 路径的陷阱（v0.1.4 新增）**：git 的 `core.quotepath` **默认为 `true`**，
> 会把非 ASCII 路径输出成「引号 + C 风格八进制转义」。实测（文件名 `中文模块.py`）：
>
> | 来源 | 得到的键 |
> |------|----------|
> | `commit.stats.files` / `git log --numstat`（默认 quotepath） | `'"\344\270\255\346\226\207\346\250\241\345\235\227.py"'` |
> | 同上，但加 `-c core.quotepath=false` | `'中文模块.py'` ✅ |
> | 扫描器（读文件系统，`as_posix()`） | `'中文模块.py'` ✅ |
>
> 两者**交集为空**，字典 join 会静默失败、历史指标全部丢失（不是报错，而是悄悄算成 0）。
> 因此**从 git 读取路径的一方（M4）必须显式关闭 quotepath**，例如以
> `git -c core.quotepath=false log --numstat …` 调用，或对取值做八进制反转义；
> 只含 ASCII 与空格的文件名不受影响（空格不会触发转义，已实测）。
> 上表「与 `git log --numstat` 对齐」的表述，严格说是指 **`core.quotepath=false` 时的对齐**。

### 4.2 确定性【契约】

同样的输入必须产出**逐字节相同**的输出（可复现性要求，Sprint 3 评估需要）：

- 文件按路径**升序**排列（`sorted`，不做本地化排序）；
- 符号按 `(lineno, name)` 升序排列；
- `RepositoryScan.scanned_at` 与 `ScanStats.elapsed_ms` 是**唯一**的非确定字段；
- 不做并发/多线程乱序聚合。

### 4.3 编码与容错

- 读取源码优先用 `tokenize.open`，即遵循 PEP 263 的 `# -*- coding: -*-` 声明；
- 解码失败时以 `errors="replace"` 降级，不抛异常；
- 判定为二进制（头部 1024 字节含 `\x00`）的文件只统计字节数，不解析结构；
- 单个文件出错**绝不影响整体扫描**，只在该文件的 `limitations` 中记录原因。

### 4.4 类型与序列化

- 所有对外数据结构均为 `dataclass(slots=True)`，并实现 `to_dict()`；
- `to_dict()` 的返回值只含 JSON 原生类型（`str/int/float/bool/None/list/dict`），M6 可直接 `json.dumps`；
- 枚举字段在 `to_dict()` 中序列化为其 `str` 值。

---

## 5. 数据结构

### 5.1 `LineCounts` —— 行数构成

| 字段 | 类型 | 说明 |
|------|------|------|
| `total` | `int` | 物理总行数 |
| `code` | `int` | 代码行 |
| `comment` | `int` | 仅注释行 |
| `docstring` | `int` | 仅文档字符串行 |
| `blank` | `int` | 空白行 |

**不变量【契约】**：`total == code + comment + docstring + blank`。
既含代码又含行尾注释的行计入 `code`（不重复计数）。

### 5.2 `SymbolInfo` —— 单个代码符号

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 符号名，如 `run` |
| `qualname` | `str` | 限定名，如 `AnalysisPipeline.run` |
| `parent` | `str \| None` | 所属符号的 `qualname`；顶层为 `None` |
| `kind` | `str` | `"class"` / `"function"` / `"method"` |
| `lineno` | `int` | 起始行（1 起，含装饰器行之前的 `def`/`class` 行） |
| `end_lineno` | `int` | 结束行 |
| `body_lines` | `int` | `end_lineno - lineno + 1`（派生属性） |
| `decorators` | `list[str]` | 装饰器源码文本，如 `["property"]` |
| `has_docstring` | `bool` | 是否有文档字符串 |
| `is_public` | `bool` | 不以 `_` 开头 |
| `params` | `int` | 形参个数（含 `*args`/`**kwargs`；类为 0） |
| `branch_count` | `int` | 分支点原始计数（定义见下） |
| `cyclomatic_complexity` | `int` | `branch_count + 1`（派生属性） |
| `nesting_depth` | `int` | 函数体内控制流最大嵌套深度 |

**`branch_count` 的精确口径【契约】**（M5 依赖，须一致）：计入以下 AST 节点，且**不递归进入嵌套的 `def`/`async def`/`lambda`/`class`**：

| 计入 | 不计入 |
|------|--------|
| `If`（`elif` 是嵌套 `If`，计 1 次，正确） | `With` / `AsyncWith` |
| `For` / `AsyncFor` / `While` | `try` 本身（只计 `ExceptHandler`） |
| `ExceptHandler` | `finally` |
| `IfExp`（三元表达式） | 普通函数调用 |
| `Assert` | 装饰器 |
| 推导式的 `if` 子句 | 类型注解 |
| `match` 的每个 `case` | |
| `BoolOp` 中除第一个操作数外的每个操作数（`a and b and c` 计 2） | |

> 这是**静态近似**，不是精确的执行路径数；M5 在使用前请确认口径可接受。
>
> 对 `kind == "class"` 的符号，`branch_count` 与 `nesting_depth` 恒为 0，`params` 亦为 0 ——
> 复杂度一律归属到具体的函数/方法，避免同一段代码被父子符号重复计入。
>
> `params` 计入 `self`/`cls`、`*args`、`**kwargs` 与仅关键字参数，不展开默认值表达式。
>
> 解析会下探到 `if`/`try`/`with` 等复合语句内部，因此 `if TYPE_CHECKING:` 与
> `try/except ImportError` 兼容分支中定义的类/函数同样会被收集。

### 5.3 `FileStructure` —— 单个文件的结构事实

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | §4.1 规范的路径 |
| `size_bytes` | `int` | 文件字节数；不可读为 `0` |
| `lines` | `LineCounts` | 行数构成 |
| `symbols` | `list[SymbolInfo]` | 符号列表（已排序） |
| `imports` | `list[str]` | 导入的模块名，去重后**排序**；相对导入保留前导点，如 `..core` |
| `limitations` | `list[str]` | 结构不完整的原因码，见 `Limitation` 枚举 |
| `parse_error` | `str \| None` | AST 解析失败的人类可读详情，形如 `"line 12: invalid syntax"` |
| `sha256` | `str \| None` | 文件内容 SHA-256（十六进制小写）；未计算为 `None` |
| `parsed` | `bool` | 是否**成功**完成 AST 结构解析（语法错误、超限、非文本、符号链接均为 `False`） |

派生属性：`symbol_count`、`class_count`、`function_count`、`max_cyclomatic_complexity`、`max_nesting_depth`。

**行数构成的粒度差异**：`parsed == False` 的文件（快速模式、非 Python 文件、语法错误，
以及处于快速模式的整个扫描）只能给出粗粒度结果——此时 `comment == 0` 且
`docstring == 0`，对应行全部计入 `code`，而 `total == code + blank` 的不变量仍然成立。

**符号链接**：默认不跟随。符号链接**文件**仍会作为候选产出（`path` 有值、
`size_bytes == 0`、`sha256 == None`、`limitations` 含 `symlink`），
以便 M6 展示真实覆盖率；符号链接**目录**则被剪枝并记入 `stats.excluded_dirs`。

`Limitation` 取值：`symlink` / `not-text` / `too-large` / `unreadable` / `unsupported-language` / `syntax-error`。

### 5.4 `ScanStats` —— 扫描统计

| 字段 | 类型 | 说明 |
|------|------|------|
| `files_seen` | `int` | 遍历见到的文件总数（含未命中后缀者） |
| `files_matched` | `int` | 命中 `include_suffixes` 的候选数 |
| `files_excluded` | `int` | 被排除规则剔除的候选数 |
| `files_emitted` | `int` | 进入 `files` 列表的数量（**= files_matched − files_excluded**） |
| `files_parsed` | `int` | AST 解析成功的数量 |
| `files_with_limitations` | `int` | 存在 `limitations` 的数量 |
| `excluded_dirs` | `list[str]` | 被剪枝的目录，**仓库根相对路径**且以 `/` 结尾（如 `pkg/__pycache__/`），已排序 |
| `total_bytes` | `int` | 全部 `files` 的字节数之和 |
| `elapsed_ms` | `float` | 扫描耗时（毫秒，**非确定字段**） |

### 5.5 `RepositoryScan` —— 顶层结果

| 字段 | 类型 | 说明 |
|------|------|------|
| `root` | `str` | 扫描根目录的绝对路径 |
| `path_base` | `str` | 路径基准目录的绝对路径（见 §4.1） |
| `scanned_at` | `str` | ISO-8601 UTC 时间戳（**非确定字段**） |
| `files` | `list[FileStructure]` | 全部结果，按 `path` 升序 |
| `stats` | `ScanStats` | 统计信息 |

便捷方法：
- `paths() -> list[str]`：全部文件路径（供 M3 遍历）
- `by_path() -> dict[str, FileStructure]`：路径索引（供 M4/M5 join）
- `to_dict() -> dict[str, Any]`

### 5.6 JSON 示例

```json
{
  "root": "E:\\project\\heatmap",
  "path_base": "E:\\project\\heatmap",
  "scanned_at": "2026-09-13T12:34:56.789012+00:00",
  "stats": {
    "files_seen": 128, "files_matched": 34, "files_excluded": 0,
    "files_emitted": 34, "files_parsed": 34, "files_with_limitations": 0,
    "excluded_dirs": [".git/", "__pycache__/"],
    "total_bytes": 91234, "elapsed_ms": 42.7
  },
  "files": [
    {
      "path": "src/githotmap/core/git.py",
      "size_bytes": 5300,
      "sha256": "9f2c1b...",
      "parse_error": null,
      "limitations": [],
      "imports": ["dataclasses", "pathlib", "subprocess", "typing"],
      "lines": {"total": 165, "code": 120, "comment": 30, "docstring": 8, "blank": 7},
      "symbols": [
        {
          "name": "GitHistory", "qualname": "GitHistory", "parent": null,
          "kind": "class", "lineno": 155, "end_lineno": 165, "body_lines": 11,
          "decorators": [], "has_docstring": true, "is_public": true,
          "params": 0, "branch_count": 0, "cyclomatic_complexity": 1,
          "nesting_depth": 0
        }
      ]
    }
  ]
}
```

---

## 6. 公共 API

```python
from githotmap.scanner import (
    RepositoryScanner,      # 门面类
    ScanConfig,             # 扫描配置
    RepositoryScan,         # 顶层结果
    FileStructure,          # 单文件结构
    SymbolInfo,             # 符号
    LineCounts,             # 行数构成
    ScanStats,              # 统计
    SymbolKind,             # 符号类型枚举
    Limitation,             # 限制原因码枚举
    ScanError,              # 扫描错误（仅根目录非法时抛）
    scan_repository,        # 便捷函数
    find_repository_root,   # 定位 Git 工作区根
)
```

### 6.1 `ScanConfig`

```python
@dataclass(slots=True)
class ScanConfig:
    include_suffixes: tuple[str, ...] = (".py",)
    exclude_patterns: list[str] = field(default_factory=list)
    use_default_excludes: bool = True
    respect_git_root: bool = True
    follow_symlinks: bool = False
    max_file_bytes: int = 2_000_000
    encoding: str = "utf-8"
    parse_structure: bool = True
    compute_hash: bool = True
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `include_suffixes` | `(".py",)` | 参与扫描的后缀；只有 `.py`/`.pyw`/`.pyi` 会做 AST 结构解析，其余只统计规模（记 `unsupported-language`） |
| `exclude_patterns` | `[]` | 用户额外排除规则，语义见 §6.3 |
| `use_default_excludes` | `True` | 是否叠加默认排除（`.git/`、`__pycache__/` 等） |
| `respect_git_root` | `True` | 是否按 §4.1 以 Git 工作区根为路径基准 |
| `follow_symlinks` | `False` | 是否跟随符号链接（默认不跟随，避免环路与重复计数） |
| `max_file_bytes` | `2_000_000` | 超过则只统计字节数，不解析结构（原因码 `too-large`） |
| `encoding` | `"utf-8"` | 兜底解码（优先遵循 PEP 263 声明） |
| `parse_structure` | `True` | 关闭后只做文件发现与规模统计（快速模式） |
| `compute_hash` | `True` | 是否计算内容 SHA-256 |

### 6.2 `RepositoryScanner`

```python
class RepositoryScanner:
    name: str = "repository-scanner"

    def __init__(self, config: ScanConfig | None = None) -> None: ...

    def scan(self, repo_path: str | Path) -> RepositoryScan:
        """扫描 repo_path 并返回 RepositoryScan。"""


def scan_repository(
    repo_path: str | Path,
    config: ScanConfig | None = None,
) -> RepositoryScan:
    """RepositoryScanner(config).scan(repo_path) 的便捷包装。"""
```

### 6.3 排除规则语义【契约】

- 采用 `fnmatch` 语义，**匹配的是 §4.1 的仓库根相对路径**；
- 以 `/` 结尾的模式表示「目录名」，只要路径中**任一层级**目录名等于该名字即命中（如 `__pycache__/` 命中 `a/b/__pycache__/c.py`）；
- 形如 `*.py`、`tests/*`、`*/generated/*` 的模式按 `fnmatch` 逐字符匹配整条路径；
- 空串模式忽略；匹配大小写敏感（由 `fnmatch` 决定，Windows 下亦按字面比较）。

**默认排除列表**：`.git/`、`__pycache__/`、`.venv/`、`venv/`、`env/`、`.tox/`、`.nox/`、`.eggs/`、`*.egg-info/`、`build/`、`dist/`、`site-packages/`、`node_modules/`、`.mypy_cache/`、`.pytest_cache/`、`.ruff_cache/`、`.ipynb_checkpoints/`、`.idea/`、`.vscode/`

### 6.4 异常

| 异常 | 触发条件 |
|------|----------|
| `ScanError` | 传入路径不存在或不是目录 |

**除此之外不抛异常**：单文件权限、编码、语法错误一律降级为 `limitations`。

---

## 7. 下游模块接入约定

### 7.1 给 Member 3（TODO Detection）

```python
scan = scan_repository(repo_path)
for path in scan.paths():                 # 已排序、已排除噪声
    # 必须用 path_base 拼接，不能用 root —— 见下方警告
    source = (Path(scan.path_base) / path).read_text(encoding="utf-8", errors="replace")
    ...                                    # 你的正则逻辑
```

> ⚠️ **勘误（v0.1.3）**：本节示例此前写的是 `Path(scan.root) / path`，**这是错的**。
> `paths()` 是相对于 `path_base`（Git 工作区根）的，而 `root` 是本次扫描传入的目录。
> 当扫描的是仓库**子目录**时二者不同，用 `root` 拼接会得到 `.../src/src/...` 这类不存在的路径。
> 实测：扫描 `<repo>/src` 时 `root=<repo>/src`、`path_base=<repo>`、`paths()[0]="src/githotmap/__init__.py"`，
> `path_base` 拼接命中真实文件，`root` 拼接则不存在。
> 正确拼接基准**始终**是 `path_base`；扫描仓库根时二者恰好相等，因此这个错误只在子目录场景暴露。

- 请用 `scan.paths()` 作为输入面，不要自己 `os.walk`——否则排除规则会与全局不一致；
- 读源码请**同时**用 `scan.parsed`/`limitations` 判断该文件是否值得读，并对单文件读取失败做降级处理
  （见 §4.3：一个文件读不动不能让整次检测挂掉）；
- 编码建议遵循 §4.3：优先 `tokenize.open()` 以尊重 PEP 263 的 `coding` 声明，而不是固定 `utf-8`，
  否则带 `# -*- coding: gbk -*-` 的文件会被读成乱码、造成漏报；
- 你的输出请以**同样的路径规范**建键，并在一个 TODO 上附加 `path` 与 `lineno`。

### 7.2 给 Member 4（Git History Analyzer）

- 你的历史指标请以 §4.1 路径建键，**不要**带 `./` 或反斜杠；
- 建议用 `scan.by_path()` 做 join，缺键时按 `0` 处理并在报告中说明覆盖率；
- **依赖声明（已由 PR #2 解决）**：本模块交付时 `pyproject.toml` 声明运行时**零第三方依赖**，与分工中你使用 GitPython 的计划冲突。该问题已由 `wangtianjing` 分支的 PR #2 解决——`dependencies` 现在为 `["GitPython>=3.1"]`。扫描器自身**不依赖 GitPython**（纯 `os`/`ast`/`tokenize`/`hashlib`），因此不受该决定影响。

### 7.3 给 Member 5（Debt Score Engine）

可直接消费的结构化特征（均已就绪）：

| 特征 | 来源 | 用途 |
|------|------|------|
| `size_bytes`、`lines.code` | `FileStructure` | 复杂度/规模 |
| `lines.comment` / `lines.code` | 同上 | 注释率（文档债） |
| `lines.docstring` | 同上 | 文档覆盖 |
| `symbols` 数量 | 同上 | 结构复杂度 |
| `max(cyclomatic_complexity)`、`sum(branch_count)` | `SymbolInfo` | 圈复杂度 |
| `max(nesting_depth)` | `SymbolInfo` | 嵌套深度 |
| `is_public` / `has_docstring` 比例 | `SymbolInfo` | 可维护性 |
| TODO 计数 | M3 产出 | 显式技术债 |
| `commits`/`churn`/`gini`/`age_days` | M4 产出 | 历史风险 |

> **权重与归一化归 M5**。扫描器只给原始事实，不做任何 0–1 归一化，避免与 `core/metrics.py` 的归一化常量重复定义。

### 7.4 给 Member 6（Flask Dashboard）

```python
from dataclasses import asdict
scan = scan_repository(repo_path)
return jsonify(scan.to_dict())          # 已是 JSON 原生类型，无需额外转换
```

- 建议在页面上单独展示 `stats`，用于说明「扫描覆盖率」；
- `stats.elapsed_ms` 可作为性能评估指标；
- `limitations` 非空的文件建议在 UI 上标记，避免评估时被误认为「无问题」。

---

## 8. 非功能需求落点

CS5351 要求每项非功能需求都要有架构设计方案与理由。扫描器可支撑以下候选：

| 候选非功能需求 | 架构设计选项 | 理由 |
|----------------|--------------|------|
| **性能**（万行级仓库扫描 < 3 秒） | ① 目录剪枝：`os.walk` 中原地修改 `dirnames` 跳过 `.git` 等；② 单次遍历，每个文件只读一次 | 避免「先 walk 收集再逐个判断排除」造成的重复 I/O；`.git` 目录通常是仓库中最大的部分 |
| **可扩展性**（支持多语言） | 后缀驱动发现 + 语言无关契约层，结构解析按语言分派 | 新增语言只需加一个解析器并注册后缀，`FileStructure` 契约不变 |
| **健壮性** | 单文件失败降级策略，`limitations` 审计 | 一个语法错误的文件不能让整个分析挂掉 |
| **可测试性** | 纯函数 + 依赖注入（`ScanConfig`） | 解析器可脱离文件系统单测；时间/哈希可注入 |
| **可复现性** | 确定性排序 + 内容哈希 | 评估契约需要可冻结、可对比的输入 |

> 采用前请与 Member 1（PM + Requirement Engineer）确认最终计入哪几项。

---

## 9. 设计取舍与已知限制

| 项 | 现状 | 说明 |
|----|------|------|
| 读工作区 vs 读 HEAD | 读**工作区** | 优点：能发现未提交的技术债；缺点：与 M4 的历史指标存在时间基准差。若需要严格对齐某个提交，建议后续增加 `git stash`/worktree 导出后再扫描 |
| 只支持 Python 结构解析 | 是 | 非 `.py` 后缀只统计规模（原因码 `unsupported-language`） |
| 圈复杂度为静态近似 | 是 | 无法反映动态分派、反射、装饰器改写的行为 |
| 不做重命名检测 | 是 | 与 `core/git.py` 的已知边界一致（未启用 `-M`） |
| 符号不含嵌套在函数内的局部类/函数？ | **包含** | 嵌套定义也会产出符号，`parent` 指向外层符号 |
| 不解析类型注解/调用图/数据流 | 是 | 超出当前范围，属后续 Sprint |

---

## 10. 扩展点与后续 Sprint 计划

- **Sprint 1（当前）**：文件发现 + Python AST 结构解析 + 单元测试。
- **Sprint 2**：多语言结构解析（JS/Go 至少一种）按语言分派；增量扫描（基于 `sha256` 跳过未变文件）。
- **Sprint 3**：把扫描器接入 `core/pipeline.py`，替换现有 `metrics.enrich_worktree_attributes`（其当前只提供 `size_bytes` 与 `lines_of_code` 两项）。

> **与现有脚手架的衔接**：`core/metrics.py::enrich_worktree_attributes` 目前自行实现了「文件大小 + 行数」，与扫描器功能重叠；`core/pipeline.py::_excluded` 亦有一份排除规则实现。建议 Sprint 3 统一收敛到扫描器，**当前 Sprint 暂不改动**以免影响既有 17 个测试。

---

## 11. 待确认事项

| # | 事项 | 需要谁确认 |
|---|------|------------|
| 1 | §4.1 路径规范是否作为全组强制契约 | M3/M4/M5/M6 |
| 2 | `branch_count` 口径（§5.2）是否满足 M5 需求 | Member 5 |
| 3 | ~~M4 使用 GitPython 与「零第三方依赖」声明的冲突如何取舍~~ | ✅ 已解决（PR #2 已将 GitPython 计入 `dependencies`） |
| 4 | 最终计入哪几项非功能需求 | Member 1 |
| 5 | `src/githotmap/py.typed` 缺失（`pyproject.toml` 已声明为 package-data）是否补齐 | Member 1 |

---

## 12. 实现状态与既有问题基线

### 12.1 本模块实现状态（Sprint 1）

| 项 | 状态 |
|----|------|
| 文件发现（含目录剪枝、确定性排序、Git 根定位） | ✅ 已实现 |
| Python AST 结构解析（符号/导入/复杂度/嵌套深度） | ✅ 已实现 |
| 行数分类（代码/注释/文档字符串/空白，四类互斥） | ✅ 已实现 |
| 容错降级（语法错误、超长、二进制、不可读、符号链接） | ✅ 已实现 |
| 单元 + 集成测试 | ✅ 76 passed / 3 skipped（skip 为 Windows 下无权限创建符号链接的用例） |
| `ruff check`（scanner 目录） | ✅ 通过 |
| `mypy --strict`（scanner 目录） | ✅ 通过 |

### 12.2 脚手架既有问题（**不是**本次引入，建议排期清理）

> 测量基准为分支点 `e177833`。PR #2 重写了 `core/git.py`，因此该文件中列的 F401 可能已被
> 一并修掉；其余条目在 PR #2 未触及的文件中，应仍然存在。

| 位置 | 问题 | 影响 |
|------|------|------|
| `core/git.py:19` | `typing.Iterable` 未使用（ruff F401） | 静态检查不通过（PR #2 后待复核） |
| `core/models.py:12` | `typing.Mapping` 未使用（ruff F401） | 静态检查不通过 |
| `core/ranking.py:22`、`core/metrics.py:71`、`config/config.py:56` | `dict` 缺类型参数（mypy `type-arg`） | mypy strict 下 3 处报错 |
| `core/metrics.py:52` | 返回 `Any`（mypy `no-any-return`） | 同上 |
| `core/scoring.py:190,217,253` | 函数缺参数类型注解（mypy `no-untyped-def`） | 同上 |
| `pyproject.toml` | 声明 `py.typed` 为 package-data，但 `src/githotmap/py.typed` 不存在 | 影响类型信息对外可见性 |

> 因此目前 `ruff check src tests` 与 `mypy src` 在**整个仓库**范围会失败，但失败项**全部**在
> 上述既有位置；scanner 模块自身是干净的。

---

## 13. 变更记录

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| v0.1 | Sprint 1 | 初稿：定义路径规范、5 个数据结构、公共 API、下游接入约定 | Member 2 |
| v0.1.1 | Sprint 1 | 依实现回填：`parsed` 字段、行数粒度差异、符号链接语义、类符号复杂度为 0、复合语句内定义、`excluded_dirs` 形态、实现状态与既有问题基线 | Member 2 |
| v0.1.2 | Sprint 1 | 依 PR #2 更新：M4 的 GitPython 依赖声明冲突已解决（§7.2、§11）；§12.2 补注测量基准 | Member 2 |
| v0.1.3 | Sprint 1 | **勘误**：§7.1 示例的拼接基准由 `scan.root` 改为 `scan.path_base`（扫描仓库子目录时前者会得到不存在的路径）；补充单文件读取降级与 PEP 263 编码两条接入要求 | Member 2 |
| v0.1.4 | Sprint 1 | §4.1 新增**非 ASCII 路径陷阱**：git `core.quotepath` 默认转义路径，会使 M4 与 M2 的键交集为空、历史指标静默丢失；M4 侧须关闭 quotepath | Member 2 |
