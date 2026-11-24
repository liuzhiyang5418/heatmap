# NFR-2 / NFR-3 实现计划与分工表

| 项目 | 内容 |
|------|------|
| 迭代 | Sprint 2（第 6–9 周） |
| 基线 | `main` @ `8f448a4`（含 PR #11），`pytest` **146 passed / 3 skipped** |
| 选定 NFR | **NFR-2 健壮性与可审计性**、**NFR-3 可复现性与可验证性** |
| 团队规模 | 6 人（课程要求 ≥2 项 NFR，本方案 2 项） |
| 文档状态 | 待会签（§8 决策点需在 W1 站会前确认） |

> 基线说明：本地最后一次 `fetch` 被中断，远端是否还有新提交未同步未知。开工前请先跑一次
> `git fetch && git log --oneline main..origin/main`，若基线变动需重新核对本计划中的行号。

---

## 1. 两项 NFR 的可度量定义

### NFR-2 健壮性与可审计性

> **陈述**：面对任意输入（坏编码、符号链接、超大文件、非 ASCII 路径、浅克隆、无权限、空仓库、二进制文件等），
> 工具**不得崩溃，也不得静默降级**——每一次降级都必须带可机器读取的原因码，且能被 UI 展示。

| 编号 | 验收指标 | 目标值 | 验证方式 |
|------|----------|--------|----------|
| NFR-2.1 | 12 类故障注入场景的崩溃率 | **0** | `tests/test_robustness.py` |
| NFR-2.2 | 被跳过/降级文件的**原因码覆盖率** | **100%**（每个都有 code） | 同上，断言 `degradations` 非空且 code 正确 |
| NFR-2.3 | 覆盖率字段可见 | `AnalysisResult.stats` 含 `files_matched / emitted / degraded` 且 HTML 可见 | HTML 快照测试 |
| NFR-2.4 | 严格模式 | `--strict` 下有降级即退出码 **3**，且打印原因码清单 | CLI 集成测试 |
| NFR-2.5 | 静默吞异常 | 业务代码中裸 `except Exception: pass` **归零** | ruff `BLE001`/`S110` 纳入 CI |

### NFR-3 可复现性与可验证性

> **陈述**：相同仓库、相同参数、相同版本下，两次运行的分析结果除显式标注的非确定字段外
> **逐字节相同**；跨平台（Windows/Linux）一致；每次结果可生成稳定指纹用于回归比对。

| 编号 | 验收指标 | 目标值 | 验证方式 |
|------|----------|--------|----------|
| NFR-3.1 | 同输入双跑 `canonical()` | **完全相等** | `tests/test_determinism.py` |
| NFR-3.2 | 冻结夹具指纹 | 3 个仓库 × 指纹一致 | `tests/test_frozen.py` |
| NFR-3.3 | 跨平台一致性 | ubuntu-latest 与 windows-latest 指纹相同 | CI matrix |
| NFR-3.4 | schema 可追踪 | `AnalysisResult.schema_version` 存在；格式变更即升版 | 单元测试 |
| NFR-3.5 | 非确定字段收敛 | 仅 `analyzed_at`、`elapsed_ms` 两类，且可由外部时钟注入 | 代码检索 + 测试 |

---

## 2. 工作包拆解（WP）

依赖图（`→` 表示前置）：

```
WP-0 ──► WP-1 ──► WP-2
  │        │
  │        └──► WP-4
  ├──► WP-5 ──► WP-7
  └──► WP-6 ──► WP-5 / WP-7

WP-10（前置缺陷）──► WP-3（故障注入依赖其完成）
WP-8（CI）与全部工作包并行
WP-9（文档）贯穿全程
```

### WP-0 诊断与统计模型【所有工作的地基】

- **新增** `src/githotmap/core/diagnostics.py`
  ```python
  class DegradationCode(str, Enum):
      # 复用 scanner 的 6 类 + 新增
      SYMLINK = "symlink"; NOT_TEXT = "not-text"; TOO_LARGE = "too-large"
      UNREADABLE = "unreadable"; UNSUPPORTED_LANGUAGE = "unsupported-language"
      SYNTAX_ERROR = "syntax-error"
      GIT_QUOTEPATH = "git-quotepath"      # 新增：M4-2 的显式原因码
      STAGE_FAILED = "stage-failed"        # 新增：某阶段整体失败
      REPO_NOT_GIT = "repo-not-git"; EMPTY_REPO = "empty-repo"
      SHALLOW_CLONE = "shallow-clone"

  @dataclass(slots=True)
  class Degradation:
      stage: str                      # git / scanner / todo / scoring
      code: DegradationCode
      path: str | None
      summary: str                    # 一行人类可读
      detail: str | None = None

  @dataclass(slots=True)
  class AnalysisStats:
      files_matched: int = 0          # git 侧见到的文件
      files_emitted: int = 0          # 进入最终结果
      files_degraded: int = 0         # 至少有一条 Degradation
      commits_seen: int = 0
      stage_elapsed_ms: dict[str, float] = field(default_factory=dict)
      degradations_by_code: dict[str, int] = field(default_factory=dict)
      def to_dict(self) -> dict[str, Any]: ...
  ```
- **修改** `core/models.py`：`AnalysisResult` 增 `stats: AnalysisStats`、`schema_version: str = "1.0"`
- **修改** `core/models.py`：`FileResult` 增 `limitations: list[str]`（与现有 `status` 并存）
- **约束**：`diagnostics.py` **不得** import `config`（避免复现 `config ⇄ core` 循环）
- **验收**：`pytest` 全绿；`to_dict()` 只含 JSON 原生类型
- **工作量**：M5，**3 h**

### WP-1 流水线降级贯通【NFR-2 核心】

- **修改** `core/pipeline.py`
  - 删除 `:99-100` 与 `:110-112` 的 `except Exception: pass`
  - 新增内部 `_guard(stage, fn, stats)` 包装：捕获异常 → 追加 `Degradation(STAGE_FAILED)` → 继续
  - 每个阶段记录 `stage_elapsed_ms`，并统计 `files_matched / files_emitted / files_degraded`
  - scanner/todo 的 per-file `limitations` 归并进 `FileResult.limitations`
- **修改** `todo/detector.py`：单文件读取失败降级（原 M3-2），失败即 `continue` 并记录 code
- **验收**：故障场景下 `stats` 数字正确、`degradations` 有内容
- **工作量**：M5 主责 4 h + M3 协作 3 h

### WP-2 严格模式【NFR-2】

- **修改** `config/config.py`：`ScoringConfig` 增 `degrade_policy: str = "degrade"`（`"degrade" | "strict"`）
- **新增** `core/diagnostics.py::AnalysisDegradedError(Exception)`，携带 `degradations`
- **修改** `core/pipeline.py::run`：`strict` 且存在降级 → 抛 `AnalysisDegradedError`
- **修改** `cli/main.py`：`analyze` 增 `--strict`；捕获 `AnalysisDegradedError` → 打印原因码清单 → `return 3`
- **验收**：CLI 集成测试断言退出码 3 与输出内容
- **工作量**：M5，**3 h**

### WP-3 故障注入测试套件【NFR-2 验收】

- **新增** `tests/test_robustness.py` + `tests/fixtures/faults.py`（动态建仓工厂，不提交二进制）
- **12 类场景**：
  1. 非 ASCII 文件名 2. 二进制文件 3. 超过 2 MB 的大文件 4. 语法错误 .py
  5. GBK/`# -*- coding -*-` 声明 6. 符号链接（Windows 下 skip） 7. 空仓库（无提交）
  8. 非 git 目录 9. 浅克隆 10. 只读文件（无权限） 11. 超深嵌套目录 12. 损坏的 git 对象
- **每个场景断言三件事**：① 不抛未捕获异常；② `degradations` 中 code 正确；③ `stats` 数字正确
- **工作量**：M6 主责 6 h + M3 协作 2 h

### WP-4 HTML 覆盖率与状态面板【NFR-2 可见性】

- **修改** `renderers/html.py`
  - 头部新增覆盖率卡片：`matched / emitted / degraded` + 按原因码分布 + 可展开的降级清单
  - 表格新增「状态」列（`ok` / `low_confidence` / `missing`），`limitations` 进 tooltip
  - **顺带修 M6-2**：表格排序与色块错位（改用 path 关联，不再用排序后索引）
- **验收**：HTML 快照测试；色块与表格行一一对应
- **工作量**：M6，**6 h**

### WP-5 确定性序列化与结果指纹【NFR-3 核心】

- **修改** `core/models.py`
  ```python
  def to_dict(self, deterministic: bool = False) -> dict[str, Any]: ...

  def canonical(self) -> str:
      """canonical JSON：排除 analyzed_at / elapsed_ms，键排序，浮点 round(6)。"""

  def fingerprint(self) -> str:
      """sha256(canonical())，十六进制小写。"""
  ```
- **规范化规则**（必须写进文档）：
  - 排除 `analyzed_at`、`elapsed_ms`、`scanned_at`
  - dict 键按 `sorted()`；list 保持既有确定性排序（scanner 已保证）
  - 浮点统一 `round(6)`；换行无关；路径统一 POSIX
- **验收**：`tests/test_determinism.py` 双跑相等；`to_dict(deterministic=True)` 不含时间字段
- **工作量**：M5，**5 h**

### WP-6 时钟与耗时注入【NFR-3】

- **新增** `core/clock.py`：`Clock` 协议（`now() -> datetime`、`monotonic() -> float`）、`SystemClock`、`FixedClock`
- **修改**：`core/models.py:203`、`scanner/models.py:226`、`scanner/scanner.py:128` 改为从注入时钟取
- **修改**：`AnalysisPipeline.__init__(config=None, clock=None)`、`scan_repository(..., clock=None)`
- **验收**：用 `FixedClock` 跑两次，`analyzed_at` 相同；代码检索 `datetime.now(` 仅出现在 `clock.py`
- **工作量**：M2 主责 4 h + M4 协作 2 h

### WP-7 冻结夹具与回归指纹【NFR-3 验收】

- **新增** `tests/fixtures/build_frozen.py`：生成 3 个固定仓库（幂等、固定提交时间与作者）
  1. 本仓库自身快照 2. 含中文文件名的小仓库（锁定 M4-2 的修复） 3. 故障注入仓（覆盖 WP-3 的场景）
- **新增** `tests/fixtures/frozen/<name>/expected.json`：`{"schema_version": "1.0", "fingerprint": "..."}`
- **新增** `tests/test_frozen.py`：跑夹具 → 断言 `fingerprint()` 相等；不一致时报出首个差异路径
- **注意**：夹具仓库提交时间必须**固定**（`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`），否则指纹会随运行日期漂移
- **工作量**：M2 主责 5 h + M6 协作 3 h

### WP-8 CI 与质量门禁【两项 NFR 的基础设施】

- **新增** `.github/workflows/ci.yml`
  - `matrix: [ubuntu-latest, windows-latest]` × `pytest`（含 `--cov`）、`ruff check`、`mypy src`、指纹一致性 job
- **修改** `pyproject.toml`：`[tool.ruff.lint]` 显式 `select`（含 `BLE001`、`S110`）；`[tool.coverage]` 阈值
- **修复存量**：ruff 35 条 → 0；mypy 21 错 → 0（`pyproject.toml` 已声明 `strict = true`，属"把声明变成事实"）
- **验收**：两个平台 × 四个 job 全绿；PR 状态检查可见
- **工作量**：M6，**7 h**

### WP-9 文档与评估契约【课程要求】

- **新增** `docs/nfr.md`：两项 NFR 的陈述、度量、架构方案、理由、验收、排除项
- **新增** `docs/evaluation-contract.md`：冻结任务 / 数据 / 基线 / 指标 / 阈值 / 测试用例（对应课程"冻结评估契约"）
- **修改** `docs/scanner-interface.md §8/§11`：NFR 从"候选"改为"定稿"，关闭待确认事项 #4
- **修改** `README.md`：目录树补 `scanner/`、`todo/`、`docs/`；补 NFR 与覆盖率说明
- **工作量**：M1，**6 h**

### WP-10 前置缺陷修复【WP-3 验收的前置条件】

| 缺陷 | 位置 | 为何必须先修 |
|------|------|--------------|
| **M4-2 非 ASCII 路径静默归零** | `core/git.py`（`git log --numstat` 取值） | 属 NFR-2 的"静默失效"典型，且故障场景 #1 直接依赖 |
| **M4-3 7 处 `Repo` 未 close** | `core/git.py:52,73`、`core/analysis.py:89,134,185,229,273` | 句柄泄漏属健壮性；也是故障场景 #12 的前置 |
| **M3-2 单文件读取无降级** | `todo/detector.py:36` | 被 WP-1 吸收，避免重复开工 |
| **M3-3 跟随符号链接** | `todo/detector.py:34-37` | 故障场景 #6 的前置 |

- **工作量**：M4 主责 6 h + M3 协作 3 h

---

## 3. 分工表

> 工时按 Sprint 2 共 4 周、每人 10–18 h 估算（合计 ≈ **78 人时**，略高于课程均值，因 M5/M6 承担核心改造）。

| 成员 | 角色 | 主责 WP | 协作 WP | 预估工时 | Sprint 2 交付物 |
|------|------|---------|---------|----------|-----------------|
| **Member 1** | PM / 需求 | **WP-9** | WP-3（场景口径）、WP-2（严格模式语义） | 10 h | `docs/nfr.md`、`docs/evaluation-contract.md`、§11 会签关闭 |
| **Member 2** | Scanner | **WP-6**、**WP-7** | WP-0（原因码对齐）、WP-10 | 14 h | 时钟注入、3 个冻结夹具 + 期望指纹 |
| **Member 3** | TODO 检测 | **WP-10（M3-2/M3-3）** | WP-1（todo 阶段降级）、WP-3 | 9 h | 检测器降级、符号链接跳过 |
| **Member 4** | Git 历史 | **WP-10（M4-2/M4-3）** | WP-6（git 侧时钟） | 11 h | quotepath 修复 + 回归测试、7 处 `Repo` 关闭 |
| **Member 5** | 评分 / 流水线 | **WP-0**、**WP-1**、**WP-2**、**WP-5** | WP-4 | 18 h | 诊断模型、降级贯通、严格模式、确定性序列化 |
| **Member 6** | Dashboard / 测试 | **WP-3**、**WP-4**、**WP-8** | WP-7 | 16 h | 故障注入套件、覆盖率面板、CI 门禁 |

**关键路径**：`WP-0 → WP-1 → WP-2`（M5 串行）与 `WP-6 → WP-7`（M2→M2/M6）。M5 是瓶颈，建议 W1 先把 WP-0 的接口冻结下来，让 M6 可以并行开发 WP-4 的 UI 骨架。

---

## 4. 周排期（Sprint 2 = 第 6–9 周）

| 周 | 主题 | M1 | M2 | M3 | M4 | M5 | M6 |
|----|------|----|----|----|----|----|----|
| **W1（第6周）** | 定契约、清前置 | `nfr.md` 初稿 | 时钟协议设计 | M3-2/3-3 | M4-2 + M4-3 | **WP-0 接口冻结** | CI 骨架 |
| **W2（第7周）** | 降级贯通 | 评估契约初稿 | WP-6 实施 | WP-1 todo 阶段 | 回归测试补全 | **WP-1** | WP-4 骨架 |
| **W3（第8周）** | 严格模式 + 注入 | 场景口径评审 | WP-7 夹具 | WP-3 协作 | 代码评审 | **WP-2 + WP-5** | WP-3 + WP-4 |
| **W4（第9周）** | 集成与验收 | 文档定稿、会签 | 夹具指纹入库 | 验收跑测 | 验收跑测 | 集成 + 修复 | CI 全绿、覆盖率 |

**每周站会必查三个数**：① 故障注入通过数 /12；② 指纹一致性是否仍绿；③ ruff+mypy 剩余告警数（目标单调降到 0）。

---

## 5. 验收清单（Sprint 2 结束时逐条打勾）

### NFR-2

- [ ] `pytest tests/test_robustness.py` —— 12 场景全绿
- [ ] 每个场景断言：默认模式退出码 0、`degradations` 含正确 code、`stats` 数字正确
- [ ] `--strict` 下故障仓退出码 **3**，标准错误打印原因码清单
- [ ] 含中文文件名的仓库：该文件 `commits > 0` 且 `score > 0`
- [ ] HTML 显示覆盖率卡片与「状态」列；色块与表格行一一对应
- [ ] `ruff check` 中 `BLE001`/`S110` 归零

### NFR-3

- [ ] `pytest tests/test_determinism.py` —— 双跑 `canonical()` 相等
- [ ] `pytest tests/test_frozen.py` —— 3 个夹具指纹一致
- [ ] CI（ubuntu + windows）四个 job 全绿，两平台指纹相同
- [ ] `to_dict(deterministic=True)` 输出不含 `analyzed_at` / `elapsed_ms`
- [ ] 全仓库仅 `core/clock.py` 出现 `datetime.now(` / `time.perf_counter(`

### 通用

- [ ] `pytest` 全量 ≥ 146 passed（新增用例只增不减）
- [ ] `ruff check src tests` = 0；`mypy src` = 0
- [ ] `docs/nfr.md` 与 `docs/evaluation-contract.md` 已合并
- [ ] 报告素材：性能/健壮性/可复现三张对比表（改造前 vs 改造后）

---

## 6. 风险与对策

| 风险 | 触发信号 | 对策 |
|------|----------|------|
| **循环依赖复发** | `import githotmap.core` 报 partially initialized | `diagnostics.py` / `clock.py` 只依赖标准库；`config` 单向下行；CI 加一条"import 冒烟" |
| **指纹跨平台漂移** | CI 两平台指纹不同 | 统一 LF、POSIX 路径、`round(6)`、固定提交时间；差异时先打印首个不同路径 |
| **浮点不稳定** | 双跑指纹偶发不同 | 固定累加顺序（按 path 排序后聚合），必要时改用整数分 |
| **覆盖率面板暴露真实失败** | 演示时页面出现一堆降级 | 这是**功能而非 bug**，但要在 README 说明口径；演示前跑一遍干净仓库 |
| **M5 成为瓶颈** | W2 结束 WP-1 未完成 | W1 冻结 WP-0 接口，WP-4 用假数据并行开发 |
| **故障场景 #6 在 Windows 无法构造** | 符号链接需要管理员权限 | 该场景标 `skipif(win32)`，只记 skip 不记失败（现有 3 skipped 同源） |
| **范围膨胀** | 有人想顺手做 NFR-1 性能 | 本 Sprint **不做**性能改造；numstat 替换留到 Sprint 3，本 Sprint 只修 quotepath 正确性 |

---

## 7. 不做的事（明确划出边界，写进报告）

| 不做 | 理由 |
|------|------|
| 性能优化（NFR-1） | 已单独立项，本 Sprint 聚焦健壮性与可复现；避免与 `git.py` 大改冲突 |
| Dashboard（Flask） | 继续用自包含 HTML；M6-4 的口径问题在 `docs/nfr.md` 中说明 |
| 多语言解析 | Sprint 3 议题 |
| 用户实验 | 属评估阶段，本 Sprint 只冻结契约 |

---

## 8. 需要会签的决策点（W1 站会前确认）

| # | 决策点 | 建议方案 | 需谁确认 |
|---|--------|----------|----------|
| 1 | 原因码是否以 `scanner.Limitation` 为唯一来源 | 是，`diagnostics.DegradationCode` 继承其取值并扩展 | M2/M3/M5 |
| 2 | `--strict` 的退出码 | **3**（0 成功、1 运行时失败、2 配置错误、3 降级） | M5/M6 |
| 3 | 确定性范围 | 排除 `analyzed_at`/`elapsed_ms`/`scanned_at`；其余必须一致 | M1/M5 |
| 4 | 冻结夹具选哪 3 个仓库 | 本仓库快照 + 含中文名仓库 + 故障仓 | M2/M6 |
| 5 | 覆盖率阈值 | 行覆盖 ≥ 70% | M1/M6 |
| 6 | 覆盖率面板信息密度 | 卡片 + 原因码分布 + 可展开清单（不做图表） | M6/M1 |

---

## 9. PR 拆分建议（11 个 PR，对应 10 个 WP）

按你们既有的 PR 审查节奏拆分，每个 PR 都挂在 NFR 编号上，便于"需求 → PR → 测试"追踪。

| PR | 分支名 | 标题 | 主要改动 | 负责人 | 依赖 | 合并前必须绿 |
|----|--------|------|----------|--------|------|--------------|
| **A** | `feat/diagnostics-model` | feat(core): 引入 Degradation / AnalysisStats 诊断模型 | `core/diagnostics.py`(新)、`core/models.py` | M5 | — | 全量 pytest；`to_dict` JSON 原生；import 冒烟 |
| **B** | `fix/git-quotepath-repo-close` | fix(git): 关闭 core.quotepath 并修复 Repo 句柄泄漏 | `core/git.py`、`core/analysis.py`、`tests/test_git.py` | M4 | — | 中文文件名 `commits > 0`；`Repo(` 与 `.close()` 配平 |
| **C** | `fix/todo-degrade-symlink` | fix(todo): 单文件读取失败降级 + 跳过符号链接 | `todo/detector.py`、`tests/test_todo_detector.py` | M3 | A | 坏文件不中断整次检测 |
| **D** | `feat/pipeline-degradation` | feat(pipeline): 降级贯通与阶段耗时统计 | `core/pipeline.py` | M5 | A、C | `stats` 数字正确；裸 except 归零 |
| **E** | `feat/strict-mode` | feat(cli): `--strict` 严格模式（退出码 3） | `config/config.py`、`core/pipeline.py`、`cli/main.py` | M5 | D | 退出码 3 + 原因码清单输出 |
| **F** | `feat/deterministic-serialization` | feat(core): `canonical()`/`fingerprint()` 与时钟注入 | `core/clock.py`(新)、`core/models.py`、`scanner/*`、`core/pipeline.py` | M5 + M2 | A | 双跑 `canonical()` 相等 |
| **G** | `test/robustness-suite` | test: 12 类故障注入套件 | `tests/test_robustness.py`、`tests/fixtures/faults.py` | M6 + M3 | B、D | **12/12 通过** |
| **H** | `feat/html-coverage-panel` | feat(render): 覆盖率面板 + 状态列 + 修复排序错位 | `renderers/html.py`、`tests/test_html.py` | M6 | D | HTML 快照；色块与行一一对应 |
| **I** | `test/frozen-fixtures` | test: 冻结夹具与指纹回归 | `tests/fixtures/build_frozen.py`、`frozen/*/expected.json`、`tests/test_frozen.py` | M2 + M6 | F | **3/3 指纹一致** |
| **J** | `ci/quality-gate` | ci: 双平台 CI + ruff/mypy 归零 | `.github/workflows/ci.yml`、`pyproject.toml`、存量告警修复 | M6 | — | 2 平台 × 4 job 全绿 |
| **K** | `docs/nfr-and-contract` | docs: NFR 定稿与冻结评估契约 | `docs/nfr.md`、`docs/evaluation-contract.md`、`README.md`、`scanner-interface.md §8/§11` | M1 | — | §11 待确认事项 #4 关闭 |

**合并顺序建议**：`B → C → A → D → E → F → G/H → I → J → K`

> B 与 C 是纯修复、互不冲突，放在最前可以先拿到两个"已验证变绿"的成果；
> A 是地基，虽然是新代码但不影响现有行为，可以先合；
> J（CI）建议在 W1 末就合并，这样后续每个 PR 都会被门禁拦住。

---

## 附：与课程的对应关系

| 课程要求 | 本计划中的落点 |
|----------|----------------|
| Sprint 2 = Sprint 1 全部活动 + **代码质量** | WP-8（ruff/mypy 归零、CI 门禁） |
| Sprint 3 = 上述 + **自动化测试、调试与维护支持** | WP-3/WP-7 的自动化测试、WP-1 的降级可诊断性为其打底 |
| NFR 需**架构方案与理由** | `docs/nfr.md`（WP-9）+ 本计划 §2 的 D1–D3 决策 |
| **冻结评估契约** | `docs/evaluation-contract.md`（WP-9）+ WP-7 指纹 |
| **需求到结果可追踪** | 每个 WP 的验收指标 ↔ NFR-2.x / NFR-3.x 编号一一对应 |
