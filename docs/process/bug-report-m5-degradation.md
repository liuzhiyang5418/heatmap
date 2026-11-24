# Bug 反馈：WP-1 / WP-2 降级统计与严格模式

| 项目 | 内容 |
|------|------|
| 反馈对象 | Member 5（WP-0 诊断模型 / WP-1 降级贯通 / WP-2 严格模式） |
| 审查基线 | `main` @ `9e74dfe`（含 PR #18 `feat/diagnostics-model` 与 PR #19 `feat/pipeline-degradation`） |
| 审查范围 | `core/diagnostics.py`、`core/pipeline.py`、`cli/main.py`、`config/config.py` |
| 审查方式 | 读码 + **独立跑数据复现**（不是只读推断） |
| 严重度 | **2 × P1**（直接卡 NFR-2 验收）+ 3 × P2/P3 |
| 反馈人 | Member 2 |
| 文档状态 | ✅ 已修复并独立复验（PR #20 → `main` @ `14a74bc`）；§3.4 由 M2 收口（`8446fc0`） |

---

## 0. 先说结论

M5 这两块的方向是对的，值得保留：

- `_guard` 取代了原来两处 `except Exception: pass`，阶段级异常不再被吞掉；
- 各阶段耗时进入 `stage_elapsed_ms`（实测 `git 3781.6ms / metrics 9.6 / scanner 9.8 / todo 6.7 / scoring 1.2`，可用）；
- `--strict` 退出码 3、原因码清单打印、`degrade_policy` 开关都已就位；
- 把 scanner 的 `limitations` 合并进 `FileResult.limitations` 这一步是对的。

但有两处实现缺口，会让 **NFR-2 的验收项直接失败**，且都是「静默」型缺陷（不报错、只是数字不对）：

| 编号 | 问题 | 违反的验收指标 | 严重度 |
|------|------|----------------|--------|
| BUG-1 | `AnalysisStats.degradations_by_code` **恒为空** | NFR-2.2 / NFR-2.3 | **P1** |
| BUG-2 | `--strict` 在 `limit` 截断时**漏报**，退出码 0 而非 3 | NFR-2.4 | **P1** |

两条都已实测，下面给出最小复现与建议修法。

---

## 1. BUG-1：`degradations_by_code` 恒为空

### 1.1 现象

构造一个有语法错误的文件，跑完整分析：

```
files_matched = 25
files_emitted = 25
files_degraded = 1
degradations_by_code = {}          ← 应该是 {"syntax-error": 1}
带 limitations 的文件 = [('zz_broken.py', ['syntax-error'])]
```

**文件级降级确实存在（`FileResult.limitations` 有值），但按码统计永远是空的。**

### 1.2 根因

`core/pipeline.py:186-187`：

```python
for d in stats.degradations:
    stats.degradations_by_code[d.code.value] = stats.degradations_by_code.get(d.code.value, 0) + 1
```

`stats.degradations` 只装**阶段级**降级（`_guard` 捕获的 `STAGE_FAILED`）。而 scanner 产出的**文件级**降级（`symlink` / `not-text` / `too-large` / `unreadable` / `unsupported-language` / `syntax-error`）从未进入这个循环——它们只被写进了 `FileResult.limitations`。

也就是说：`AnalysisStats` 有两个降级通道（阶段级 `degradations`、文件级 `FileResult.limitations`），但按码统计只扫了第一个。

### 1.3 影响

- NFR-2.2「被跳过/降级文件的原因码覆盖率 100%」无法被验证——统计口径拿不到这些码；
- NFR-2.3「覆盖率字段可见」：M6 的覆盖率面板会渲染出一个全 0 的分布图；
- 演示时页面会显示「没有降级」，而实际上有文件没被解析——这正是 NFR-2 要消灭的「静默失效」，只不过从日志层搬到了统计层。

### 1.4 建议修法

把**文件级**通道也并进统计。建议遍历 `files`（未截断的全量）而不是 `ranked_files`：

```python
# 7. 统计降级分布
degradations_by_code: dict[str, int] = {}
for d in stats.degradations:                     # 阶段级
    degradations_by_code[d.code.value] = degradations_by_code.get(d.code.value, 0) + 1
for f in files:                                  # 文件级（注意：用 files，不是 ranked_files）
    for code in f.limitations:
        degradations_by_code[code] = degradations_by_code.get(code, 0) + 1
stats.degradations_by_code = degradations_by_code
```

> 如果希望键集合稳定（便于 NFR-3 指纹比对、M6 直接渲染），可以按 `DegradationCode` 的顺序补 0。M2 的分支 `feat/scanner-diagnostic-codes` 在 scanner 侧已经提供了 `scan.stats.degradations_by_code`（键集固定），接进来也行——但**直接遍历 `files` 更通用**，能同时覆盖 git/todo 注入的码，不依赖扫描器。

### 1.5 验收方式

```
扫描含 1 个语法错误文件的仓库 → stats.degradations_by_code == {"syntax-error": 1}
扫描干净仓库 → 所有计数为 0（键集可决定是否固定）
```

---

## 2. BUG-2：`--strict` 在 `limit` 截断时漏报

### 2.1 现象

同一故障仓库（25 个文件，1 个 `zz_broken.py` 有语法错误）：

| 命令 | 实际退出码 | 期望 |
|------|-----------|------|
| `analyze --strict --limit 1` | **0** ❌ | **3** |
| `analyze --strict --limit 50` | 3 ✅ | 3 |
| `analyze`（默认模式） | 0 ✅ | 0 |

`--strict --limit 1` 时 stderr 完全为空——它认为**没有任何降级**，直接成功退出。

### 2.2 根因

`core/pipeline.py:188`：

```python
stats.files_degraded = sum(1 for f in ranked_files if f.limitations) + len(stats.degradations)
```

用的是 `ranked_files`，而它是 `rank_files(files, limit=...)` 的**截断结果**（`pipeline.py:181`）。降级文件一旦被排除在 top-N 之外，就永远不会被统计到。

`stats.files_degraded = 0` → `pipeline.py:191` 的 strict 判断为假 → 不抛 `AnalysisDegradedError` → CLI 返回 0。

默认 `limit=20`，中型仓库很容易踩中：只要降级文件排名在 20 名之后就会漏报。

### 2.3 影响

- NFR-2.4「`--strict` 下有降级即退出码 3」**不成立**；
- 更麻烦的是它的失败方式是「**看起来通过了**」：CI 里跑 `--strict` 会变绿，但仓库其实有文件没被解析。这正是 NFR-2 语境下最不能接受的一类缺陷；
- 依赖 `stats.files_degraded` 的任何展示/门禁都会低估降级数量。

### 2.4 建议修法

用全量 `files` 替代 `ranked_files`：

```python
stats.files_degraded = sum(1 for f in files if f.limitations) + len(stats.degradations)
```

顺序上要注意：这一行必须在 `rank_files()` **之后**仍然能拿到 `files`——目前它在第 186 行，`files` 仍在作用域内，直接替换即可。

### 2.5 顺带的语义问题

同一行的 `+ len(stats.degradations)` 把「文件级降级文件数」和「阶段级降级条数」相加，两个量纲不同：

- `f.limitations` 统计的是**文件个数**；
- `stats.degradations` 统计的是**事件条数**（一次阶段失败算 1 条）。

同一个量可能会被重复计量（某阶段失败 → 该阶段产出为空 → 恰好也导致文件级为 0，目前是巧合平衡）。建议拆成两个字段，或明确只统计文件级：

```python
stats.files_degraded = sum(1 for f in files if f.limitations)
```

并把阶段级失败单独暴露（`degradations` / `degradations_by_code` 里已有）。

### 2.6 验收方式

```
故障仓库（降级文件不在 top-N）+ --strict --limit 1  → 退出码 3 + 打印原因码清单
干净仓库 + --strict                                  → 退出码 0
非 git 目录 + --strict                               → 退出码 3（stage-failed）
```

---

## 3. 其它问题（P2 / P3，不阻塞验收但建议一并处理）

### 3.1【P2】`_guard` 捕获异常后变量未初始化 → 后续会 `NameError`

`pipeline.py` 的 `metrics_map`（第 105 行）、`files`（第 163 行）都在 `with _guard(...)` 块内定义。`_guard` 只捕获异常、不让程序停止，因此异常发生后：

- `metrics_map` 未定义 → 第 119 行 `metrics_map.items()` 抛 `NameError`；
- `files` 未定义 → 第 181 行 `rank_files(files, ...)` 抛 `UnboundLocalError`。

也就是说 `_guard` 本想「降级后继续」，但实际会在下游崩掉，且**抛出的是未捕获的 `NameError` 而非 `AnalysisDegradedError`**。

建议在 `run()` 开头把这些变量初始化：

```python
metrics_map: dict[str, FileMetrics] = {}
files: list[FileResult] = []
scan: RepositoryScan | None = None
```

> 这条是【静态】结论（读码推断），我没构造出能真实触发 scoring/metrics 阶段失败的仓库。但变量作用域是确定的，建议顺手加固。

### 3.2【P3】`_guard` 缺返回类型注解

```
src\githotmap\core\pipeline.py:29: error: Function is missing a return type annotation  [no-untyped-def]
```

`pyproject.toml` 声明 `strict = true`，这一条是本次新增的 mypy 报错（合并前 18 错，合并后 19 错）。建议改为：

```python
@contextmanager
def _guard(stage: str, stats: AnalysisStats) -> Iterator[None]:
```

### 3.3【P3】三处残留的草稿注释

这几行看起来像编辑过程中的临时标注，不像是要进仓库的内容：

| 文件 | 行 | 内容 |
|------|-----|------|
| `core/diagnostics.py` | 81 | `# 原来的 __all__ 改成：` |
| `cli/main.py` | 92 | `# 这行必须在` |
| `cli/main.py` | 95 | `# ⬇️ 这一行必须要有，而且和 except 对齐！` |
| `config/config.py` | 115 | `# 添加这一行，默认是宽容的 degrade，如果设为 strict 就会在降级时报错` |

建议删除或改写成解释「为什么」的说明（例如 `# strict 策略下任何降级都视为失败，见 docs/nfr.md NFR-2.4`）。

### 3.4【P3】`diagnostics.py` 的原因码与 scanner 不同源 —— ✅ 已收口

`DegradationCode` 的前 6 个值原先是**硬编码字面量**，与 `scanner.Limitation` 各存一份：

| 位置 | 修复前的定义 |
|------|--------------|
| `scanner/models.py` | `Limitation`：6 个扫描阶段码 |
| `core/diagnostics.py:17-22` | `DegradationCode`：同样 6 个（复制），再追加 5 个 |

这是 Sprint 2 决策点 #1 明确要消除的漂移风险（和 M4-2 的 `core.quotepath` 属同一类：没有异常，只是某天悄悄对不上）。

**已由 M2 在 `feat/scanner-diagnostic-codes` 收口**（提交 `8446fc0`）：

```python
from githotmap.scanner import Limitation

class DegradationCode(str, Enum):
    SYMLINK = Limitation.SYMLINK.value   # 引用唯一来源，不再复制字面量
    ...
```

配套措施：

- 新增 `tests/test_diagnostics_consistency.py`（7 用例），锁定扫描阶段码与 `scanner.Limitation`
  **同值同序**、扩展码不与扫描码撞名、以及 `AnalysisStats` 与 `ScanStats` 的计数一致
  （含「不重复计数」的防回归断言）；
- 依赖方向固化为 `core → scanner`，并写进 `core/diagnostics.py` 与
  `docs/scanner-interface.md §4.5`，防止未来成环。

---

## 4. 与 M2（scanner 侧）的接口说明

M2 的 `feat/scanner-diagnostic-codes` 分支（待合并）提供两样东西，可以简化 BUG-1 的修法：

1. `scanner.LIMITATION_CODES`（`tuple[str, ...]`，唯一来源，已锁定取值与顺序）；
2. `scan.stats.degradations_by_code`（扫描阶段按码计数，键集固定为上述 6 个，未命中记 0）。

M5 可以直接取用，作为 `AnalysisStats.degradations_by_code` 在扫描阶段的贡献；但**推荐仍以遍历 `files` 为主**（见 §1.4），因为那样也能覆盖 git/todo 注入的码，且不产生跨模块耦合。

---

## 5. 修复优先级建议

| 顺序 | 项 | 理由 |
|------|----|------|
| 1 | BUG-2（strict 漏报） | 它会让 CI 在「看起来绿」的情况下放过有降级的仓库，风险最高 |
| 2 | BUG-1（统计恒空） | 卡 NFR-2.2/2.3，且是 M6 覆盖率面板的数据源 |
| 3 | §3.1 变量初始化 | 一行防御，避免 `_guard` 失效时抛 `NameError` |
| 4 | §3.2 / §3.3 | mypy 与代码整洁，可随同一个 PR 一起清 |

---

## 6. 验收清单（M5 已修复，M2 独立复验通过）

> 复验基线：`main` @ `14a74bc`（PR #20 `fix/m5-degradation-strict`，提交 `12b69ec`）。
> 复验方式：用本文件附录 A 的脚本**独立重建故障仓库**，不复用 M5 的测试用例，
> 避免「用自己的测试证明自己的实现」这种循环论证。

| 验收项 | 结果 | 证据 |
|--------|------|------|
| 故障仓库（降级文件不在 top-N）`--strict --limit 1` → 退出码 3，stderr 含原因码 | ✅ | 退出码 **3**，stderr 输出 `- syntax-error: 1 处`；修复前为 0 且 stderr 为空 |
| 干净仓库 `--strict` → 退出码 0 | ✅ | 不抛错，`files_degraded=0`，`degradations_by_code={}` |
| `stats.degradations_by_code` 含文件级码，且与 `FileResult.limitations` 一致 | ✅ | `{'syntax-error': 1}`；修复前恒为 `{}` |
| `stats.files_degraded` 不随 `--limit` 变化 | ✅ | `limit=20` 与 `limit=100` 均为 1 |
| `mypy src` 错误数回到 18 | ✅ | 18 错 / 6 文件；修复前 19 错 / 7 文件 |
| 全量 `pytest` 全绿，且新增针对上述两点的回归测试 | ✅ | **198 passed / 4 skipped**；新增 `tests/test_pipeline_degradation.py`（7 用例） |

### 6.1 修复后的质量水位

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| `pytest` | 190 passed / 4 skipped | **198 passed / 4 skipped** |
| `ruff check src tests` | 25 条 | **19 条** |
| `mypy src` | 19 错 / 7 文件 | **18 错 / 6 文件** |

### 6.2 逐条对照

| 反馈条目 | 状态 | 修复方式 |
|----------|------|----------|
| BUG-1 `degradations_by_code` 恒为空 | ✅ 已修 | 新增遍历 `files` 的 `limitations` 并入统计 |
| BUG-2 `--strict` 受 limit 截断漏报 | ✅ 已修 | `files_degraded` 与 strict 判断改用全量 `files` |
| §2.5 `files_degraded` 语义混乱 | ✅ 已修 | 只统计文件级；阶段级走 `degradations` |
| §3.1 `_guard` 后变量未初始化 | ✅ 已修 | `run()` 开头初始化 `records`/`metrics_map`/`files`/`seed_mode` |
| §3.2 `_guard` 缺返回类型注解 | ✅ 已修 | `-> Iterator[None]` |
| §3.3 三处草稿注释 | ✅ 已修 | 全部删除/改写 |
| §3.4 `DegradationCode` 与 scanner 不同源 | ✅ 已收口 | 由 M2 在 `feat/scanner-diagnostic-codes` 改为引用 `scanner.Limitation` |

**结论**：2 个 P1 与 §3.1–§3.3 均已修复并经独立验证，NFR-2.2 / NFR-2.3 / NFR-2.4 的实现缺口关闭。

> 另注：M5 的修复顺带改善了 CLI 输出（strict 模式现在会打印 `按码统计`）、
> 整理了两处 import，并给 `except Exception` 补了有正当理由的 `noqa`，
> 这几项不在本次反馈范围内，一并记录以便追溯。

---

## 附录 A：复现脚本（Windows / 本机环境）

```powershell
$env:PYTHONPATH="E:\project\.pydeps;E:\project\heatmap\src"
$env:GIT_CONFIG_COUNT="2"
$env:GIT_CONFIG_KEY_0="safe.directory"; $env:GIT_CONFIG_VALUE_0="E:/project/heatmap"
$env:GIT_CONFIG_KEY_1="safe.directory"; $env:GIT_CONFIG_VALUE_1="*"
cd E:\project\heatmap
```

```python
# 建一个「24 个正常文件（提交多、排名靠前）+ 1 个语法错误文件（排名靠后）」的仓库
import subprocess, sys
from pathlib import Path
root = Path(r"E:\project\.tmp\faultyrepo"); root.mkdir(parents=True, exist_ok=True)
def git(*a):
    subprocess.run(["git", *a], cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
git("init", "-q", ".")
for i in range(24):
    for c in range(3):
        (root / f"ok{i}.py").write_text(f"def f{i}():\n    return {c}\n", encoding="utf-8")
        git("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", f"c{c}")
(root / "zz_broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
git("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "add broken")

# BUG-2
p = subprocess.run([sys.executable, "-m", "githotmap", "analyze",
                    "--repo-path", str(root), "--strict", "--limit", "1"])
print("BUG-2 退出码应为 3，当前为", p.returncode)

# BUG-1
from githotmap.core.pipeline import AnalysisPipeline
r = AnalysisPipeline().run(str(root), mode="hot", limit=100)
print("degradations_by_code =", r.stats.degradations_by_code, " (应为 {'syntax-error': 1})")
print("files_degraded       =", r.stats.files_degraded, " (应为 1)")
print("带 limitations 的文件 =", [(f.path, f.limitations) for f in r.files if f.limitations])
```

## 附录 B：本次审查的基线数据

| 项 | 数值 |
|----|------|
| 基线提交 | `9e74dfe` |
| `pytest` | 190 passed / 4 skipped |
| `ruff check src tests` | 25 条（合并前 27，−2） |
| `mypy src` | 19 错 / 7 文件（合并前 18 / 6，**+1** 即 §3.2） |
| 阶段耗时实测 | git 3781.6ms / metrics 9.6ms / scanner 9.8ms / todo 6.7ms / scoring 1.2ms |
