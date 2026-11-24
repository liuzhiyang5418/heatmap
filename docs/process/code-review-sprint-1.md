# Sprint 1 代码审查报告与分工建议

| 项目 | 内容 |
|------|------|
| 审查对象 | `main` @ `454f038`（含 PR #2/#4/#5/#6/#7 与 `wangtianjing` 的合并结果） |
| 审查日期 | Sprint 1 末 |
| 审查方式 | 3 个独立只读审查（按模块）+ 对关键结论的**独立数值/行为复现** |
| 文档作者 | Member 2（Repository Scanner） |
| 文档状态 | 待各模块负责人认领与回复 |

---

## 1. 文档目的

本文档汇总 Sprint 1 代码审查的全部发现，**按负责人分派**，供团队在 Sprint 2 排期。
每条发现标注了**可信度等级**，请按等级决定投入：

| 标记 | 含义 |
|------|------|
| **【已验证】** | 审查者本人用真实数据/真实仓库**跑出了现象**，附复现命令，可信度最高 |
| **【静态】** | 通过阅读代码与推理得出，**尚未跑数据验证**；请负责人先复现再动手 |
| **【待定口径】** | 不是代码 bug，而是需要团队先统一语义/口径才能决定怎么改 |

> 请勿直接依据【静态】条目改动代码——报告中已明确标注哪些结论未经运行验证。

---

## 2. 审查方法与局限

**做了什么**：

- 按模块拆分给 3 个独立审查者（TODO 检测 / Git 历史分析 / 评分引擎），各自只读、不改动任何文件；
- 审查者被要求给出 `文件:行号`、问题成因、**最小反例**，并明确区分「确认缺陷」与「待确认疑点」；
- 对报告中最严重的结论，文档作者另行**独立复现**（见各条的「复现」小节），**不采信未复现的结论**。

**没做什么（重要）**：

- 审查者所在的执行环境**没有可用的 Python 解释器**（`python` 是 WindowsApps 占位符），因此**未能运行 pytest**；
- 所以凡是依赖运行时行为的结论，已逐条标注；本项目的实际解释器在 `E:\anacoda\python.exe`（见 §8）。

---

## 3. 已在 Sprint 1 修复的项

以下 4 项已由 Member 2 修复并推送到 `main`，**无需再处理**：

| 提交 | 内容 | 复现依据 |
|------|------|----------|
| `e559d7a` | 勘误 `docs/scanner-interface.md` §7.1：拼接基准 `scan.root` → `scan.path_base` | 见 §4.2 |
| `4269365` | 修 `todo/detector.py` 的路径拼接，扫描仓库子目录不再崩溃 | 见 §4.2 |
| `454f038` | `tests/test_analysis.py` 边界用例改用显式时间戳 `2026-09-20T00:00:00Z` | 见 §4.3 |
| `ac5aa55` | `docs/scanner-interface.md` §4.1 补入非 ASCII 路径陷阱（v0.1.4），为 M4-2 的修复提供契约依据 | 见 §4.3 |

修复后全量测试：**119 passed / 3 skipped / 0 failed**。

> **责任说明**：§4.2 的成因是 `docs/scanner-interface.md` §7.1 的示例代码写错，被 Member 3 照抄实现。
> 文档与代码均已修正，特此记录以免重复归因。

---

## 4. 发现速览

### 4.1 按负责人汇总

| 负责人 | 高 | 中 | 低/待定 | 说明 |
|--------|----|----|---------|------|
| Member 3（TODO 检测） | 1 | 1 | 4 | §5 |
| Member 4（Git 历史分析） | 1（已验证） | 4 | 4 | §6 |
| Member 5（评分引擎） | 1（已验证） | 3 | 8 | §7 |
| Member 2（仓库扫描器） | 0 | 0 | 0 | 扫描器代码**未发现缺陷**；仅文档已修正 |
| Member 1 / Member 6 | — | 1 | 1 | §9（工程流程类） |

### 4.2 Member 3 —— TODO Detection Module

#### M3-1【已验证 · 已修复】`detector.py` 路径拼接基准错误

- **位置**：`src/githotmap/todo/detector.py:36`（原）
- **问题**：用 `Path(scan.root) / path` 读取源码，但 `scan.paths()` 返回的是相对 `scan.path_base` 的路径。扫描 Git 工作区**子目录**时 `root != path_base`，拼出多层重复目录。
- **复现**（修复前）：

  ```
  扫描 <repo>       -> OK，38 条
  扫描 <repo>/src   -> FileNotFoundError: ...\src\src\githotmap\__init__.py
  ```

- **状态**：已修复（`4269365`）。

#### M3-2【已验证 · 未修复】`detect()` 缺少单文件读取失败的降级

- **位置**：`src/githotmap/todo/detector.py:36`
- **问题**：`read_text(..., errors="replace")` 只兜**解码**错误，不兜 `FileNotFoundError` / `PermissionError` / `IsADirectoryError`。任一文件读取失败会中断**整次检测**，与模块自身 docstring「单文件出错不影响整体检测」及 `docs/scanner-interface.md` §4.3 的契约相反。
- **最现实的触发路径**：**失效的符号链接**（见 M3-3）——扫描器对 symlink 只登记不读内容，`detect()` 却会去读它。
- **建议修法**：循环体内包 `try/except OSError`，失败即 `continue` 并记录；可复用扫描器已有的 `limitations` 机制。
- **工作量**：小。

#### M3-3【静态 · 未修复】`detect()` 会跟随符号链接读取

- **位置**：`src/githotmap/todo/detector.py:34-37`
- **问题**：扫描器**有意**不读符号链接内容（只登记路径、`size_bytes=0`、`limitations=["symlink"]`，见接口文档 §5.3），但 `scan.paths()` 包含它们，`detect()` 会直接读取，可能读到仓库外文件或失效目标。
- **建议修法**：跳过 `limitations` 含 `symlink` / `too-large` / `not-text` 的条目，或在 `detect()` 内检查 `scan.by_path()[path].parsed`。
- **工作量**：小。

#### M3-4【已验证 · 未修复】词法失败降级时，字符串内的 `#TODO` 被误报

- **位置**：`src/githotmap/todo/parser.py:47-50`
- **问题**：`tokenize` 失败（文件有语法错误）时退化为「任何含 `#` 的行算注释」，于是字符串字面量里的标记被当成技术债。
- **复现**：

  ```python
  iter_todos("c.py", 'def broken(:\n    pass\nmsg = "#TODO 这不是注释"\n')
  # -> 误报 1 条 TODO
  ```

- **影响**：仅影响**语法错误**的文件；正常文件不受影响。
- **工作量**：小。

#### M3-5【已验证 · 未修复】docstring 描述的尾部引号残留

- **位置**：`src/githotmap/todo/parser.py:81-84`
- **复现**：`"""TODO: 重构这个函数"""` → `description == '重构这个函数"""'`
- **建议修法**：截断/剥离尾部引号序列。
- **工作量**：小。

#### M3-6【静态 · 未修复】`detector` 未按文件大小设限

- **位置**：`src/githotmap/todo/detector.py`
- **问题**：扫描器对 >2 MB 文件标 `too-large` 且不解析，`detect()` 仍会全量读取并正则扫描。
- **工作量**：小。

#### M3-7【待定口径】标记匹配的松紧

- **位置**：`src/githotmap/todo/parser.py:26`（`\b(TODO|FIXME|HACK|XXX)\b` + `IGNORECASE`）
- **说明**：审查提出「普通词误报」，但**经实测该担忧被夸大**——`\b` 生效，`hackathon`、`TODOING` 均**不会**误报。真正需要定的是口径问题：散文中孤立的 `hack`/`xxx` 算不算技术债。
- **一个现成的例子**：`src/githotmap/scanner/__init__.py` 的模块 docstring 写了「不提取 TODO/FIXME（M3）」，于是**扫描器自己的文档被检测器报成技术债**。这说明「docstring 中的标记」这一策略需要明确边界。
- **建议**：由 Member 3 与 Member 5 会签后写进 `docs/todo-interface.md`。

#### M3-8【待定口径】编码口径与扫描器不一致

- **位置**：`src/githotmap/todo/detector.py:36` 固定 `encoding="utf-8"`
- **问题**：扫描器遵循 PEP 263（`tokenize.open`），检测器固定 UTF-8。带 `# -*- coding: gbk -*-` 的文件会被读成乱码 → **漏报**。
- **建议**：统一走 `tokenize.open()`。
- **工作量**：小。

---

### 4.3 Member 4 —— Git History Analyzer

> **本节第 1 条已在 Sprint 1 由 Member 2 修复**（见 §3），此处保留完整记录以便追溯。

#### M4-1【已验证 · 已修复】裸日期 `since` 的语义误解

- **位置**：`tests/test_analysis.py:126-133`（测试），根因在 `src/githotmap/core/analysis.py:97-100` 把 `since` 原样传给 `iter_commits`
- **问题**：git 对裸日期 `"2026-09-20"` 会用**当前时刻的时分秒 + 本机时区**补齐时间部分，**不是当天 00:00**。原测试注释的前提与事实相反。
- **复现**：本机 `+08:00`、`19:29` 时逐分钟采样 —— `--since=2026-09-20` 恰好保留阈值之后 `+1/+2/+3` 分钟的提交（阈值 = `2026-09-20 11:29:24 UTC`），排除阈值本身及其之前。故该用例**只在本地时间 18:00 之前通过**，且随机器时区变化。
- **影响面（不止测试）**：任何用户通过 `--since` 传裸日期，得到的都是「当天当前时刻」这个意外边界。
- **状态**：测试已改为显式 `2026-09-20T00:00:00Z`（`454f038`）。
- **仍建议**：在 `compute_score`/`analysis` 入口**把裸日期规范化为显式时间**，或在 CLI 帮助里明确要求传完整时间戳——否则同样的坑会以「用户拿到意外结果」的形式复现。
- **工作量**：小。

#### M4-2【已验证 · 未修复 · 建议优先】非 ASCII 文件名导致跨模块 join 完全失败

- **位置**：`src/githotmap/core/git.py:91`、`src/githotmap/core/analysis.py:192,235`（`commit.stats.files` 的键）
- **问题**：git 的 `core.quotepath` **默认为 `true`**，会把非 ASCII 路径输出为「引号 + C 风格八进制转义」。因此 M4 的键与扫描器（读文件系统得到的真实 UTF-8 路径）**交集为空**。
- **复现**（实测，仓库内文件名为 `中文模块.py`）：

  | 来源 | 得到的键 |
  |------|----------|
  | `commit.stats.files` / `git log --numstat`（默认） | `'"\344\270\255\346\226\207\346\250\241\345\235\227.py"'` |
  | 加 `-c core.quotepath=false` | `'中文模块.py'` ✅ |
  | 扫描器 `scan.paths()` | `['中文模块.py']` ✅ |

  ```
  M4 键 ∩ scanner 键 = 空集
  ```

- **严重性说明**：文档**将此项从审查初判的「低」上调为「高」**。理由：它不是报错，而是**静默失效**——这些文件的历史指标（commits/churn/贡献者/年龄）全部算成 0，热力图上看不出异常。本工具的目标是分析**任意**仓库，中文项目文件名非 ASCII 属常见情形。
- **建议修法**：M4 侧显式关闭 quotepath（如以 `git -c core.quotepath=false log --numstat …` 调用），或对取值做八进制反转义。含空格的文件名**不受影响**（已实测，空格不触发转义）。
- **契约依据**：`docs/scanner-interface.md` §4.1（v0.1.4，已提交 `ac5aa55`），含实测对照表与
  M4 侧的修法要求。
- **工作量**：小。

#### M4-3【已验证 · 未修复】所有 `git.Repo` 打开后从不 `close()`

- **位置**：`src/githotmap/core/git.py:52,73`；`src/githotmap/core/analysis.py:89,134,185,229,273`（共 **7 处**）
- **验证方式**：全树检索 `Repo(` 得到 7 处；检索 `.close()` 在 `src/` 下**零命中**。
- **问题**：GitPython 的 `Repo` 会惰性持有常驻的 `git cat-file --batch` 子进程（读 `commit.author` / `commit.stats.files` 即触发）。这些函数 `return` 前都不关，每次调用泄漏一个进程及其对 `.git` 的句柄。
- **讽刺之处**：`tests/test_analysis.py` 的 fixture 注释里已经承认「Windows 下临时目录可能删不掉」并做了 `repo.close()`，但只关了 fixture 自己建的 Repo，被测函数内部新开的没关。
- **建议修法**：`try/finally` 或上下文管理器统一处理。
- **工作量**：小（7 处机械改动）。

#### M4-4【静态 · 未修复】三种时区口径并存

- **位置**：`analysis.py:281-287` 用 `commit.committed_datetime`（提交自身时区）做 day/hour 分组；`git.py:84` 用 `.timestamp()`（UTC epoch）；`--since` 用**本机时区**
- **问题**：同一个 UTC 时刻、不同作者的提交可能落入**不同**的 day/hour 桶；`commit_frequency` 与 heatmap 的 age/recent 口径也对不上。
- **建议**：统一转 UTC 后再分组，与 metrics 层对齐。
- **工作量**：中（需先定口径）。

#### M4-5【静态 · 待定口径】merge 提交的 churn 归属

- **位置**：`git.py:86`、`analysis.py:103,192,235`
- **问题**：`commit.stats` 对**第一父**做 diff，merge 会把「带入的第二父分支全部改动」计给 merge 者，可能既重复计数又错误归属。
- **建议**：明确用 `--first-parent` 遍历，或显式跳过 merge（`len(commit.parents) > 1`）并在文档说明口径。
- **工作量**：中。

#### M4-6【静态 · 未修复】浅克隆会崩溃

- **位置**：`git.py:86`；异常只包住了 `Repo()` **构造**（`git.py:72-75`），迭代内异常会冒出
- **问题**：浅克隆边界提交的父对象不存在，`commit.stats` 对缺失父做 diff 会抛 `GitCommandError` → 整次 analyze 失败。审查者已实测浅克隆中 `git rev-parse HEAD^` 报 `unknown revision`。
- **注意**：`git log --numstat` **本身能**处理浅克隆，是「逐提交 diff」这条路径才崩。
- **建议**：捕获边界异常并降级；或在文档中明确不支持浅克隆。
- **工作量**：中。

#### M4-7【静态 · 低】其余

- `analysis.py:137` `repo.branches` 是否包含远程跟踪分支需确认（docstring 称「本地分支」）；
- `analysis.py:199` `exclude_paths` 用 `pat in path` 子串匹配（未文档化，语义过宽）；当前 CLI 不传该参数，影响有限；
- `iter_commits()` 默认只走 HEAD（`git.py:82`、`analysis.py:100,190,233,280`），未合并分支的历史不进指标，与 `branch_activity` 的独立枚举口径不一致；
- `tests/test_git.py:48-56` 去重键 `(author, timestamp, file_path)` 缺 commit hash，同秒同作者改同一文件会误判重复；
- `tests/test_git.py:38-45` 的 `since` 断言只验证下界，且注释同样把裸日期当成 00:00 UTC（属「空转」测试，建议与 M4-1 一并修正）。

---

### 4.4 Member 5 —— Debt Score Engine

#### M5-1【已验证 · 未修复 · 建议优先】`breakdown` 不是「百分比贡献」

- **位置**：`src/githotmap/core/scoring.py:168`
- **问题**：`breakdown = {key: value * 100.0 …}` 存的是**归一化指标 × 100**，而分数是 `Σ weight × value × 100`（`scoring.py:157-158`）。`core/models.py` 对 `breakdowns` 的注释明确写的是「**百分比贡献**」——实现与自身契约不符。
- **复现**（实测，默认权重）：

  | 模式 | score | sum(breakdown) | 非零权重键数 |
  |------|-------|----------------|--------------|
  | hot | 17.91 | **120.53** | 5 |
  | risk | 48.13 | **281.53** | 7 |
  | complexity | 38.97 | **196.53** | 6 |
  | roi | 24.79 | **120.58** | 4 |

  饱和算例最能说明问题：**score = 100.0000，而 sum(breakdown) = 500.00**（5 个键各显示 100）。

- **展示失真**（HOT，已换算为实际分值）：

  | 信号 | breakdown 显示 | 权重 | 实际贡献 | 实际占比 |
  |------|---------------|------|----------|----------|
  | age | 69.58（最大） | 0.10 | 6.96 分 | 39% |
  | churn | 16.00 | 0.40 | 6.40 分 | 36% |
  | commits | 8.00 | 0.40 | 3.20 分 | 18% |
  | contrib | 25.00 | 0.05 | 1.25 分 | 7% |
  | size | 1.95 | 0.05 | 0.10 分 | 1% |

  低权重的 `contrib` 看起来是第三大贡献，实际只占 7%。热力图若按 breakdown 做风险分解，会**直接误导用户**。

- **建议修法**：改为加权百分比贡献 `weight_i × value_i / Σ(weight × value) × 100`，使其**和 ≈ 100 且与分数一致**；需同步修改 `tests/test_scoring.py:151-160`（该断言目前把错误语义**固化**为期望值），以及依赖 breakdown 的理由生成逻辑（见 M5-4）。
- **工作量**：小改动 + 需同步测试与理由生成。

#### M5-2【已验证 · 未修复】可配置归一化上限 `caps` 无校验

- **位置**：`src/githotmap/core/scoring.py:110-121`
- **复现**：

  ```
  caps={'commits': 0.0}     -> ZeroDivisionError: division by zero
  caps={'age_days': -1.0}   -> ValueError: expected argument value > -1, got -1.0
  caps={'commits': -500.0}  -> 不崩溃，但分数从 17.91 静默降到 14.71（该信号被废掉）
  ```

- **为何重要**：`caps` 是 PR #5 **新增并通过 `ScoringConfig.normalization_caps` 正式暴露**的入口，文档鼓励用它按仓库规模调整饱和点——却没有任何校验。
- **建议修法**：入口处对每个 cap 校验 `> 0`，非法值明确报错（而非静默归零或崩溃）。
- **工作量**：小。

#### M5-3【已验证 · 未修复】全负权重产生负分

- **位置**：`scoring.py:77-80`（`_normalize_weights` 在 `total <= 0` 时原样返回）+ `scoring.py:155-158`
- **复现**：`weights={CHURN:-1.0, LOC:-2.0}`，RISK 模式 → **`score = -50.00`**，而 `severity = low`
- **问题**：违反「分数必须落在 0–100」的不变量；且 breakdown 仍显示正值（churn=40、loc=5），与负分自相矛盾。docstring 声称此时「得分趋近 0」，实际是负分。
- **建议修法**：`total <= 0` 时报错或返回全 0，并 clamp 基础模式分数（当前只有复合模式 clamp，见 M5-9）。
- **工作量**：小。

#### M5-4【静态 · 未修复】复合模式的理由会与复合等级矛盾

- **位置**：`scoring.py:173-174`（基础模式在 critical/high 时插入 `Severity: high（… 分），建议优先处理。`）+ `scoring.py:315-316`（复合模式原样拼接基础模式理由）
- **算例**：`hot=60`（high）+ `risk=30`（medium）→ `active_owners = 45`（**medium**），但其理由首条正文是 `[hot] Severity: high（60 分），建议优先处理。` —— 一个 medium 文件被建议「优先处理」。
- **修法**：复合理由不应复用带等级前缀的基础理由；等级前缀应只在最终模式上生成。
- **工作量**：中。

#### M5-5【静态 · 待定口径】`size_bytes == 0` 把「已删除文件」与「空文件」混为一谈

- **位置**：`scoring.py:103-104`（`if metrics.size_bytes == 0: return ScoreResult(0.0, …)`），结合 `metrics.py:149-151`（工作区不存在的文件 `stat()` 失败 → `size_bytes = 0`）
- **问题**：历史上提交上千次、churn 极高的**已删除文件**会得 0 分并从排序中消失，与真正的空文件无法区分。代码并未显式排除删除文件，而是**靠这个副作用「意外」归零**。
- **需团队先定口径**：产品是否只关心当前工作区文件？若是，应**显式**排除并接受历史热点丢失；若否，删除文件应仍按历史指标评分。
- **工作量**：中（取决于口径）。

#### M5-6【静态 · 未修复】理由基于未加权的 breakdown，低权重信号可触发高警示

- **位置**：`scoring.py:186-224`（`significant=20` / `dominant=30` 阈值作用于未加权的 breakdown）
- **算例**：RISK 模式下 `lines_of_code=10000` 而其它信号为 0 → `score ≈ 5.02`（low），理由却输出「Structural Complexity: 高代码行数增加维护者的认知负担」。
- **说明**：这是 M5-1 的**次生问题**；修好 breakdown 语义后应一并复核这些阈值。
- **工作量**：小（随 M5-1 一起）。

#### M5-7【静态 · 未修复】测试形同虚设

- **位置**：`tests/test_scoring.py:276-281` `test_high_score_gets_severity_reason_prefix`
- **问题**：`make_metrics()` 默认值在 HOT 模式下 `score ≈ 17.9`（low），故 `if sr.severity in ("critical","high")` **恒为 False**，断言体从不执行——测试通过但不验证任何东西。
- **建议**：改用明确构造的高分输入。
- **工作量**：小。

#### M5-8【静态 · 低】`_normalize_blend` 的两处边界

- `scoring.py:290,294`：`blend=[]` 时进入回退分支 `1.0 / len(blend)` → `ZeroDivisionError`（防御性缺失）；
- `scoring.py:288-290`：`blend=[(HOT,0.0),(RISK,0.5)]` 会回退为等权 `{HOT:0.5, RISK:0.5}` —— 用户想「排除 HOT」反而使其占 50%；测试 `test_normalize_blend_fallback_on_invalid_weights` 固化了该行为。需明确「0 权重」是合法排除还是非法输入。

#### M5-9【静态 · 低】其余

- `scoring.py:158` 基础模式分数未 clamp，而 `scoring.py:281` 复合模式有 clamp，口径不一致（浮点尾差理论上可越过 100）；
- `metrics.py:38-39` `gini([5]) == 0.0`，单贡献者本应是「完全集中」（RISK 靠 `inv_contrib` 部分兜底，两个所有权信号互相抵消）；
- `metrics.py:25-31` `clamp` 不处理 NaN：`NaN` 分数会被 `score_grade` 静默判为 `low`，而非报错；
- `ranking.py:14-16` 排序无次级键（`sorted` 稳定，**不**随机化、可复现，但同分顺序「看起来任意」）；`ranked[:limit]` 会丢弃与第 `limit` 名同分的项。

#### M5-10【待定口径】权重自动归一化会掩盖配置错误

- `scoring.py:72-80`：把 `0.40` 误写成 `4.0` 会被静默归一化为 `≈0.54`；负权重被静默归零（`max(w, 0.0)`）。默认四组权重和**精确为 1.0**（已逐项核对无误），故默认路径无影响。需定「便利 vs 暴露配置错误」的取向。

---

## 5. 已确认无问题的部分

审查同时确认了以下方面**没有问题**，请勿过度改动：

| 方面 | 结论 |
|------|------|
| 评分权重与复合配比 | 4 个基础模式权重和**精确为 1.000000**，3 个复合配比均归一，无零/负权重，枚举全覆盖 |
| `decay_weight` / `gini` / `clamp` 底层实现 | 正确，含 `days_old < 0` 与 `total == 0` 的处理 |
| 归一化临界点 | `x == cap` 时 `clamp` 返回 1.0，恰好饱和行为正确 |
| 排序可复现性 | `sorted` 稳定，同分不随机化 |
| 空仓库 / 无提交 / `since` 全过滤 | 返回 `[]` 或空结构，不崩溃 |
| `dominant_ratio` | 恒在 `[0,1]`（churn 非负 + `total == 0` 跳过），无除零、无越界 |
| 路径契约（**常规文件名**） | `commit.stats.files` 键为仓库根相对 POSIX、无 `./` 前缀，与扫描器一致（非 ASCII 为例外，见 M4-2） |
| TODO 正则 | 无灾难性回溯；大小写、`#TODO`、`# TODO:`、行尾注释、多标记、字符串排除、空文件、确定性排序均正确**且有测试覆盖** |
| 扫描器模块（M2） | 三份审查均**未发现缺陷**；`ruff` 与 `mypy --strict` 在 `src/githotmap/scanner/` 下全部通过 |

---

## 6. 建议的 Sprint 2 分工与优先级

> 排序原则：**先修「静默算错」的，再修「工程质量」的**。

### 第一梯队 —— 影响交付物正确性，建议优先

| 编号 | 负责人 | 问题 | 工作量 |
|------|--------|------|--------|
| M4-2 | Member 4 | 非 ASCII 路径键 → 历史指标静默全丢 | 小 |
| M5-1（+M5-6） | Member 5 | `breakdown` 语义错误 → 热力图分解误导用户 | 小 |
| M3-2 + M3-3 | Member 3 | `detect()` 崩溃路径 + symlink 跟随 | 小 |

### 第二梯队 —— 工程健壮性

| 编号 | 负责人 | 问题 | 工作量 |
|------|--------|------|--------|
| M4-3 | Member 4 | 7 处 `Repo` 未 close | 小 |
| M5-2 + M5-3 | Member 5 | `caps` 校验 + 全负权重报错 | 小 |
| M3-4 + M3-5 + M3-6 | Member 3 | 降级误报、尾引号、大小限制 | 小 |
| M5-7 | Member 5 | 空转测试 | 小 |
| M4-1 收尾 | Member 4 | 入口规范化裸日期 | 小 |

### 第三梯队 —— 需先统一口径

| 编号 | 负责人 | 需先确定什么 |
|------|--------|--------------|
| M4-4 | Member 4 | 时区口径统一为 UTC？ |
| M4-5 / M4-6 | Member 4 | merge 提交与浅克隆的处理策略 |
| M5-5 | Member 5 | 是否只分析当前工作区文件 |
| M3-7 / M3-8 / M5-8 / M5-10 | M3 + M5 | 标记匹配口径、编码口径、0 权重语义 |

---

## 7. 建议的工程流程改进（Member 1 / Member 6）

| 项 | 现状 | 建议 |
|----|------|------|
| **无 CI** | 仓库无 `.github/workflows`，`ruff` 与 `mypy` 全靠人自觉 | 增加最小 CI：`pytest` + `ruff check` + `mypy src`。当前 `ruff` 有 **6 个未使用导入**，`mypy --strict` 有 **22 个错误 / 7 个文件**（`core/analysis.py` 占 13 个），而 `pyproject.toml` 声明了 `strict = true` 却从未满足 |
| **静态检查无守门** | 上述问题长期无人拦 | 让 CI 成为 PR 的必过状态检查（对应该课程「用状态检查让证据在评审时可见」的要求） |
| **README 未同步** | 目录树仍是最初版本，缺 `scanner/`、`todo/`、`docs/` | Sprint 2 更新 |
| **接口文档未会签** | `docs/scanner-interface.md` §11 有 4 条待确认事项 | 建议 Sprint 2 开场会签 |

---

## 8. 复现环境

本机可用的解释器**不在 PATH 上**，审查者因此未能运行测试：

```powershell
# 解释器（Anaconda，Python 3.14.6 + pytest 9.0.3）
E:\anacoda\python.exe

# 运行全部测试
cd E:\project\heatmap
& "E:\anacoda\python.exe" -m pytest

# 静态检查
& "E:\anacoda\python.exe" -m ruff check src tests --output-format=concise
& "E:\anacoda\python.exe" -m mypy src
```

> 备注：在受限沙箱中跑 pytest 需要放宽权限——pytest 以 `mode 0o700` 创建 `tmp_path`，
> 沙箱会把这类目录变成不可访问。普通开发机无此问题。

---

## 9. 关于 Member 2（本文档作者）的说明

为保证归因清晰，特此声明：

- **`src/githotmap/scanner/` 的代码未发现任何缺陷**，三份审查均未在该目录提出问题；
- §4.2 的 M3-1 由**本文档作者提供的文档示例错误**引发（`docs/scanner-interface.md` §7.1 原写 `scan.root`），已修正文档与对应代码并推送（`e559d7a` + `4269365`）；
- `docs/scanner-interface.md` §4.1 原称路径「与 `git log --numstat` 对齐」，该表述在 `core.quotepath` 默认开启时**不成立**。已补入非 ASCII 路径陷阱的完整说明与实测对照表（v0.1.4，提交 `ac5aa55`）；
- 上述两项均为**文档问题**；本文档所列其余条目**均不由扫描器模块造成**，作者未擅自改动其他模块的代码。

---

## 10. 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | Sprint 1 | 初版：汇总 3 份模块审查、独立复现结论、按负责人分派与优先级建议 |
