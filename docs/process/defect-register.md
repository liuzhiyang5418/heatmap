# githotmap 缺陷总结与分工建议

| 项目 | 内容 |
|------|------|
| 审查基线 | `main` @ `30b5a69`（已含 PR #8/#9/#10 与 PR #10 回退修复） |
| 测试状态 | `pytest` **119 passed / 3 skipped**（3 skipped 为 Windows 无法创建符号链接） |
| 静态检查 | `ruff check src tests` **35 条**；`mypy src` **21 错 / 7 文件**（`pyproject.toml` 声明了 `strict = true`） |
| 文档作者 | 本次核查（基于 Sprint 1 审查报告 + 独立复现） |
| 文档状态 | 待各模块负责人认领，用于分工讨论 |

## 0. 如何使用本文档

每条缺陷标注**可信度**，请按等级决定投入，不要直接把【静态】条目当 bug 改：

| 标记 | 含义 |
|------|------|
| **【已验证】** | 本次核查或 Sprint 1 审查中**跑出了现象**，附复现方式，可信度最高 |
| **【静态】** | 通过读码与推理得出，**尚未运行验证**，请负责人先复现 |
| **【待定口径】** | 不是代码 bug，需要团队先统一语义才能动手 |

严重度：**P0** = 破坏基本功能承诺／阻断交付；**P1** = 静默算错或体验失真；**P2** = 工程质量；**P3** = 小瑕疵。

---

## 1. 结论速览

| 模块 | 负责人 | P0 | P1 | P2 | P3 | 待定口径 |
|------|--------|----|----|----|----|----------|
| M4 Git 历史分析 | Member 4 | 1（**M4-2**） | 1 | 1 | 2 | 2 |
| M3 TODO 检测 | Member 3 | 0 | 1 | 3 | 1 | 2 |
| M5 评分引擎 | Member 5 | 0 | 2 | 2 | 3 | 2 |
| M6 可视化与测试 | Member 6 | 0 | 2 | 1 | 0 | 0 |
| M2 仓库扫描器 | Member 2 | 0 | 0 | 0 | 0 | 0 |
| M1 过程与交付物 | Member 1 | 3 | 1 | 0 | 0 | 0 |

> M2 扫描器代码本身**未发现缺陷**（Sprint 1 三份独立审查一致结论）；问题集中在 M4 的路径口径与 M1 的过程交付物。

**只有 1 个 P0**：`M4-2` 非 ASCII 路径导致历史指标静默归零。建议本次会议**优先拍板它的负责人与修复时点**，其余按模块认领。

---

## 2. P0 阻断项

### M4-2 非 ASCII 文件名导致历史指标静默全丢【已验证 · 本次实测复现】

- **位置**：`src/githotmap/core/git.py`（`git log --numstat` 取值侧）、`src/githotmap/core/analysis.py:192,235`
- **根因**：git 的 `core.quotepath` 默认为 `true`，会把非 ASCII 路径输出成「引号 + C 风格八进制转义」；扫描器（读文件系统）得到的是真实 UTF-8 路径，两侧**键交集为空**。
- **实测**（本次建了一个含 `中文模块.py` 的临时仓库）：

  ```
  git 侧键    : ['"\344\270\255\346\226\207\346\250\241\345\235\227.py"', 'ascii_module.py']
  scanner 侧键: ['ascii_module.py', '中文模块.py']
  交集        : ['ascii_module.py']          ← 中文文件彻底失配

  流水线输出：
    path='"\344\270\255\346\226\207\346\250\241\345\235\227.py"'  commits=2  loc=0  cc=0  score=0.0
    path='ascii_module.py'                                      commits=1  loc=1  cc=0  score=0.3
  ```

- **影响**：中文命名的文件结构/TODO 信号全丢、`size_bytes=0` → **分数恒为 0、路径在热力图上显示为乱码**。这不是报错而是**静默失效**，热力图上完全看不出异常。而本工具的目标是分析**任意** Git 仓库，中文项目属于常见情形。
- **建议修法**：M4 侧显式关闭 quotepath（`git -c core.quotepath=false log --numstat …`，或对取到的键做八进制反转义，两者取一并写测试）。契约依据见 `docs/scanner-interface.md` §4.1（v0.1.4 已写入该陷阱与对照表）。
- **工作量**：小（约 1 处配置 + 1 个回归测试）。
- **验证方式**：新建含中文文件名的仓库跑 `analyze`，断言该文件 `commits > 0` 且 `score > 0`。

---

## 3. 按模块详表

### M4 —— Git History Analyzer（Member 4）

| 编号 | 严重度 | 可信度 | 问题 | 位置 | 建议修法 | 工作量 |
|------|--------|--------|------|------|----------|--------|
| **M4-2** | **P0** | 已验证 | 非 ASCII 路径键失配 → 指标静默归零 | `core/git.py`、`core/analysis.py:192,235` | 关闭 `core.quotepath` + 回归测试 | 小 |
| **M4-3** | P1 | 已验证 | **7 处 `git.Repo` 打开后从不 `close()`**（本次复查：`src/` 下 `Repo(` 7 处、`.close()` 0 处），GitPython 会常驻 `git cat-file --batch` 子进程，逐次泄漏进程与 `.git` 句柄 | `core/git.py:52,73`；`core/analysis.py:89,134,185,229,273` | `try/finally` 或上下文管理器统一关闭 | 小（7 处机械改动） |
| **M4-6** | P2 | 静态 | **浅克隆会崩溃**：异常只包住 `Repo()` 构造，迭代内对缺失父做 diff 会抛 `GitCommandError`，整次 analyze 失败 | `core/git.py:72-75,86` | 捕获边界异常降级，或文档明确不支持浅克隆 | 中 |
| M4-1 | P3 | 已验证 | 裸日期 `--since` 被 git 补成「当天当前时刻」而非 00:00，用户拿到意外边界（测试已改显式时间戳，**入口未规范化**） | `core/analysis.py:97-100` | 入口把裸日期规范化为显式 UTC 时间，或 CLI 帮里要求完整时间戳 | 小 |
| M4-7 | P3 | 静态 | ① `exclude_paths` 用子串匹配（语义过宽）；② `iter_commits` 默认只走 HEAD，未合并分支不进指标，与 `branch_activity` 口径不一致；③ `tests/test_git.py` 去重键缺 commit hash | 多处 | 分别定口径后修 | 小～中 |
| M4-4 | 待定 | 静态 | **三种时区口径并存**：`committed_datetime`（提交自身时区）做 day/hour 分组、`.timestamp()`（UTC epoch）算年龄、`--since` 用本机时区 | `analysis.py:281-287`、`git.py:84` | 先定「统一 UTC 后分组」再改 | 中 |
| M4-5 | 待定 | 静态 | **merge 提交的 churn 归属**：`commit.stats` 对第一父做 diff，会把带入的分支改动全计给 merge 者（重复计数 + 错误归属） | `git.py:86`、`analysis.py:103,192,235` | 定口径：`--first-parent` 或显式跳过 merge | 中 |

### M3 —— TODO Detection（Member 3）

| 编号 | 严重度 | 可信度 | 问题 | 位置 | 建议修法 | 工作量 |
|------|--------|--------|------|------|----------|--------|
| **M3-2** | P1 | 已验证 | `detect()` **缺少单文件读取失败的降级**：`errors="replace"` 只兜解码，不兜 `FileNotFoundError`/`PermissionError`/`IsADirectoryError`，任一文件失败会中断**整次检测**，与自身 docstring 和 §4.3 契约相反 | `todo/detector.py:36` | 循环内 `try/except OSError: continue` 并记录 | 小 |
| M3-3 | P2 | 静态 | 会**跟随符号链接**读取（扫描器有意不给 symlink 内容，`paths()` 却包含它们），可能读到仓库外文件或失效目标 | `todo/detector.py:34-37` | 跳过 `limitations` 含 `symlink`/`too-large`/`not-text` 的条目 | 小 |
| M3-4 | P2 | 已验证 | 词法降级时（文件有语法错误）退化为「含 `#` 的行即注释」，**字符串里的 `#TODO` 被误报** | `todo/parser.py:47-50` | 降级时收紧判定或直接跳过该文件 | 小 |
| M3-5 | P2 | 已验证 | docstring 尾部引号残留：`"""TODO: 重构这个函数"""` → `description == '重构这个函数"""'` | `todo/parser.py:81-84` | 剥离尾部引号序列 | 小 |
| M3-6 | P3 | 静态 | 未按文件大小设限：>2 MB 文件扫描器已标 `too-large`，检测器仍全量读取正则扫描 | `todo/detector.py` | 复用扫描器 `limitations` 跳过 | 小 |
| M3-7 | 待定 | 已验证 | **标记匹配口径**：`\b(?:TODO\|FIXME\|HACK\|XXX)\b` 无普通词误报（`hackathon`/`TODOING` 已实测不误报），但「散文里的孤立 hack/xxx 算不算技术债」需定口径。现成例子：`scanner/__init__.py` 的 docstring 写了「不提取 TODO/FIXME（M3）」，于是**扫描器自己的文档被检测器报成技术债** | `todo/parser.py:26` | 与 M5 会签后写进 `docs/todo-interface.md` | 小 |
| M3-8 | 待定 | 静态 | **编码口径不一致**：检测器固定 `encoding="utf-8"`，扫描器遵循 PEP 263（`tokenize.open`）→ 带 `# -*- coding: gbk -*-` 的文件被读成乱码 → 漏报 | `todo/detector.py:36` | 统一走 `tokenize.open()` | 小 |

### M5 —— Debt Score Engine（Member 5）

| 编号 | 严重度 | 可信度 | 问题 | 位置 | 建议修法 | 工作量 |
|------|--------|--------|------|------|----------|--------|
| **M5-1** | P1 | 已验证 | **`breakdown` 不是「百分比贡献」**：`breakdown[key] = 归一化值 × 100`，而分数是 `Σ 权重 × 归一化值 × 100`，因此 `sum(breakdown) ≠ score`，与 `models.py` 的注释契约矛盾。饱和算例：`score = 100` 而 `sum(breakdown) = 500` | `core/scoring.py`（`breakdown = {key: value * 100.0 …}`） | 改为加权贡献 `w×v / Σ(w×v) × 100`；**需同步** `tests/test_scoring.py:151-160` 与理由生成阈值（见 M5-6） | 小～中 |
| **M5-2** | P1 | 已验证 | 可配置归一化上限 `caps` **无任何校验**：`caps={'commits':0.0}` → `ZeroDivisionError`；负值静默废掉该信号 | `core/scoring.py`（`c = {**DEFAULT_CAPS, **caps}`） | 入口校验每个 cap `> 0`，非法值明确报错 | 小 |
| M5-4 | P2 | 静态 | **复合理由与复合等级自相矛盾**：`_composite_reasoning` 直接拼接基础模式理由，其中含 `Severity: high（60 分），建议优先处理。`；于是 `hot=60 + risk=30 → active_owners=45（medium）` 的文件会显示「建议优先处理」 | `core/scoring.py:_composite_reasoning` | 等级前缀只在最终模式生成；复合理由不带基础等级前缀 | 中 |
| M5-6 | P2 | 静态 | 理由阈值（`significant=20`/`dominant=30`）作用在**未加权**的 breakdown 上，低权重信号可触发高警示（`loc=10000` 其余为 0 → `score≈5`，理由却报「Structural Complexity」） | `core/scoring.py:_compute_reasoning` | 随 M5-1 一并复核阈值 | 小 |
| M5-7 | P3 | 已验证 | **空转测试**：`test_high_score_gets_severity_reason_prefix` 中 `make_metrics()` 在 HOT 下约 17.9 分（low），`if sr.severity in ("critical","high")` 恒为 False，断言体从不执行——测试通过但不验证任何东西 | `tests/test_scoring.py:276-281` | 改用明确构造的高分输入 | 小 |
| M5-9 | P3 | 静态 | ① `ranking.py:14-16` 无次级排序键，同分顺序「看起来任意」（`sorted` 稳定、可复现）；② `ranked[:limit]` 丢弃与第 limit 名同分的项；③ `metrics.clamp` 不处理 NaN，NaN 分数被静默判为 `low` | `core/ranking.py`、`core/metrics.py:25-31` | 加次级键 + NaN 校验 | 小 |
| M5-10 | P3 | 静态 | 权重自动归一化会**掩盖配置错误**（`0.40` 误写成 `4.0` 被静默归一为 `≈0.54`；负权重被静默归零）。默认四组权重和精确为 1.0，故默认路径不受影响 | `core/scoring.py:_normalize_weights` | 定「便利 vs 暴露错误」取向 | 小 |
| M5-5 | 待定 | 静态 | **「已删除文件」与「空文件」混为一谈**：`size_bytes == 0` 一律归零（P2 已加 `status="missing"`，但 0 字节的**真实空文件**同样被判 missing） | `core/scoring.py:compute_score` | 先定产品口径：是否只关心当前工作区文件 | 中 |
| M5-8 | 待定 | 已验证 | ① `blend=[]` 的 `ZeroDivisionError` **已在本次合并修复中消除**；② `blend=[(HOT,0.0),(RISK,0.5)]` 仍回退为等权（用户想「排除 HOT」反而使其占 50%），该行为已被测试固化 | `core/scoring.py:_normalize_blend` | 定「0 权重 = 合法排除」还是「非法输入」 | 小 |

### M6 —— Dashboard 与测试（Member 6）

| 编号 | 严重度 | 可信度 | 问题 | 建议修法 | 工作量 |
|------|--------|--------|------|----------|--------|
| **M6-1** | P1 | 已验证 | **新字段已算但不展示**：`status`/`confidence`（PR #10 引入）与 `folders`（目录聚合，实测 13 个目录）都写进了 HTML 的 JSON，但模板完全没有渲染它们——目录聚合白算，评估方案里「识别数据缺失文件」「找高分比例最高的目录」两个任务无法用界面完成 | HTML 增加：状态列/置信度标记、目录层级视图、图例口径说明 | 中 |
| **M6-2** | P1 | 静态 | **表格排序与色块错位**：`renderTable` 会重排表格行，但色块永不重排；行 `mouseenter` 用「排序后索引」去找 `.cell[data-index=i]`，点其他列排序后**悬浮到 A 行会高亮 B 色块** | 色块与表格共用同一排序结果，或按 path 而非 index 关联 | 小 |
| M6-3 | P2 | 已验证 | 无任何自动化门禁：仓库没有 `.github/workflows`；`pyproject.toml` 声称 `mypy strict = true` 却从未满足（21 错 / 35 条 ruff） | 最小 CI：`pytest` + `ruff check` + `mypy src` 三个 status check | 小 |
| M6-4 | P2 | 已验证 | 仓库里**没有 Flask Dashboard**，而 `scanner-interface.md` 与 `todo-interface.md` 都把 M6 写成「Flask Dashboard」，两份文档 §7 还给出了 `jsonify(...)` 的接入示例 | 与 M1 确认口径：本期以自包含 HTML 为宿主，还是补 Flask；若改口径需同步两份接口文档 | 待定 |

### 流水线（M5 / 集成侧）

| 编号 | 严重度 | 可信度 | 问题 | 位置 | 建议修法 | 工作量 |
|------|--------|--------|------|------|----------|--------|
| **PL-1** | P2 | 已验证 | **静默吞异常**：scanner 与 todo 的接入段都是 `except Exception: pass`（ruff `S110`/`BLE001` 共 4 条），失败时结构/SATD 信号静默变 0，与 M4-2 同类的「静默失效」风险，热力图上看不出异常 | `core/pipeline.py:98-100,110-112` | 至少记录失败原因与覆盖率并透出到 `AnalysisResult`，供 M6 展示扫描覆盖率 | 小 |
| PL-2 | P3 | 已验证 | `--preset` 与 `--mode` 的优先级只在注释里说明；复合模式下 `config.mode` 仍是默认值，靠 `pipeline.run(mode=...)` 兜底，行为正确但易误读 | `cli/main.py:70-90` | 加一句 CLI 帮助说明或显式覆盖 `config.mode` | 小 |

---

## 4. 需要先会签的「待定口径」（不认领代码，先定语义）

| 编号 | 需要决定什么 | 谁参与 |
|------|--------------|--------|
| M4-4 | 时区是否统一为 UTC 后再做 day/hour 分组 | M4 + M5 |
| M4-5 | merge 提交的 churn 归属：`--first-parent` / 跳过 merge | M4 + M5 |
| M5-5 | 是否只分析当前工作区文件；已删除文件是否仍按历史指标评分 | M5 + M1 |
| M5-8 | 配比权重为 0 是「合法排除」还是「非法输入」 | M5 |
| M3-7 | 标记匹配口径：散文里的孤立 hack/xxx、docstring 中的标记是否计入 | M3 + M5 |
| M3-8 | 编码口径统一到 `tokenize.open()`（PEP 263） | M3 + M2 |
| M6-4 | 本期宿主是自包含 HTML 还是 Flask Dashboard | M1 + M6 |

---

## 5. Sprint 1 交付物缺口（M1 主导）

代码之外，课程对 Sprint 1 的硬性要求目前**多数没有落库**：

| 编号 | 严重度 | 缺失项 | 现状证据 | 建议 |
|------|--------|--------|----------|------|
| **P-1** | **P0** | **用户故事 / 需求文档** | 全仓库检索「用户故事 / user story」零命中；README 只有功能表，没有「用户 + 场景 + 验收标准」 | 补一份 user stories（每条带验收条件），作为后续 issue 与 PR 的追踪起点 |
| **P-2** | **P0** | **非功能需求定稿** | `docs/scanner-interface.md §8` 只列「候选」5 项，`§11 #4` 仍写「最终计入哪几项非功能需求 — 待 Member 1 确认」 | 6 人队至少 2 项 NFR，每项含度量方式 + 架构方案 + 理由；作为 Sprint 2 的评估契约冻结 |
| **P-3** | **P0** | **每周仓库证据 / 过程记录** | 无 CHANGELOG、无 issue、无 Sprint 计划、无站会与燃尽图记录；`工程记录/code-review-sprint1.md`（423 行）与 `scanner-interface-v0.1.4-未提交修订.md` **都在仓库之外**，未提交 | ① 把两份审查文档提交进仓库（如 `docs/reviews/`）；② 建 issue 模板与 Sprint 看板；③ 每周留一份站会+燃尽图记录 |
| P-4 | P1 | README 与元数据未同步 | README 目录树缺 `scanner/`、`todo/`、`docs/`（「scanner」「todo」在 README 中出现 **0 次**）；`pyproject.toml` 声明 MIT 但**无 LICENSE 文件**；声明 `py.typed` 为 package-data 但文件不存在 | 更新 README；补 LICENSE 与 `src/githotmap/py.typed` |

---

## 6. 已关闭 / 本次已修复（**不要重复派活**）

| 项 | 处理 |
|----|------|
| **PR #10 覆盖式回退** | `9e7fb69` 基于旧副本重写 `scoring.py`，删掉 `ScoreResult`、`_normalize_weights`、`compute_recency_signal`、`_compute_reasoning`、`score_files`、`compute_composite_score`、`_normalize_blend`、`_composite_reasoning` 并改写三个函数签名，同时触发 `config ⇄ core` 循环导入（CLI 与 `examples/demo.py` 均无法启动、22 个评分测试无法收集）。**已在 `30b5a69` 修复**：以 PR #9 版为准恢复结构，并叠加 P2 特性（自定义阈值、缺失数据状态、近因降档、小样本置信度、基础分 clamp），已推送到 `origin/main` |
| M5-3 全负权重产生负分 | 随上述修复：基础模式分数已 clamp 到 0–100，不再出现 `-50` 分（但 breakdown 仍显示正值，见 M5-1） |
| M5-8 ① `blend=[]` 除零 | 随上述修复：`_normalize_blend` 增加空列表保护 |
| 扫描器模块（M2）缺陷 | Sprint 1 三份独立审查**均未发现缺陷**；本次复查亦无新增 |
| Sprint 1 已修的 4 项 | `e559d7a`（§7.1 拼接基准勘误）、`4269365`（M3-1 路径拼接崩溃）、`454f038`（`test_analysis` 时间戳依赖）、`ac5aa55`（§4.1 非 ASCII 陷阱） |

---

## 7. 建议分工与排期

### 第一梯队（本次会议就要定人）

| 项 | 建议负责人 | 理由 | 工作量 |
|----|-----------|------|--------|
| M4-2 非 ASCII 路径 | Member 4 | 唯一 P0 代码缺陷，需改自己模块的 git 调用 | 小 |
| P-1 用户故事 / P-2 NFR 定稿 | Member 1 | 课程硬性交付物，且是后续 issue 的追踪起点 | 中 |
| P-3 过程证据入库 + M6-3 CI | Member 6 + Member 1 | 课程评分项「每周证据」与「状态检查让证据可见」 | 小～中 |

### 第二梯队

| 项 | 建议负责人 | 工作量 |
|----|-----------|--------|
| M4-3（7 处 `Repo` 未 close）+ M4-6（浅克隆） | Member 4 | 小 / 中 |
| M3-2 + M3-3（崩溃路径 + symlink）+ M3-5 | Member 3 | 小 |
| M5-1 + M5-6（breakdown 语义与理由阈值）+ M5-2（caps 校验）+ M5-7 | Member 5 | 中 |
| M6-1 + M6-2（UI 展示新字段 + 排序错位） | Member 6 | 中 |
| PL-1（静默吞异常改为记录覆盖率） | Member 5 | 小 |

### 第三梯队（先会签口径，再排期）

M4-4、M4-5、M5-5、M5-8、M3-7、M3-8、M6-4 —— 见 §4。

---

## 附：复现命令（本机环境）

```powershell
# 环境：本机只有 Python 3.15，依赖已装在 E:\project\.pydeps
$env:PYTHONPATH="E:\project\.pydeps;E:\project\heatmap\src"
$env:GIT_CONFIG_COUNT="1"
$env:GIT_CONFIG_KEY_0="safe.directory"
$env:GIT_CONFIG_VALUE_0="E:/project/heatmap"

cd E:\project\heatmap
python -m pytest                                  # 119 passed / 3 skipped
python -m ruff check src tests --output-format=concise   # 35 条
python -m mypy src                                # 21 错 / 7 文件

# 端到端冒烟
python -m githotmap analyze --repo-path . --mode roi --output-file out.html
python -m githotmap analyze --repo-path . --mode refactor_now --output-file out2.html
python -m githotmap history --repo-path . --top-n 3
```

> 注：仓库属主 SID 与当前用户不同，git 需 `safe.directory`；shell 访问 GitHub 需走本机代理
> `127.0.0.1:7897` 且强制 `http.sslBackend=openssl`（schannel 报 `SEC_E_NO_CREDENTIALS`）。
