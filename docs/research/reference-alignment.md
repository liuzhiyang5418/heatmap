# 与参考实现 hotspot 的评分语义对照

本文回答一个问题：**githotmap 的分数与参考工具 hotspot 的分数，在什么条件下可比？**

结论先说：`hot`、`risk`、`roi` 三种模式的权重、归一化口径、时间衰减与降权规则**逐项相同**，
因此这三个模式的分数与 hotspot 同义可比；`complexity` 模式**同名异义**，分数不可直接对比。
另有若干处是我们主动改写的语义，见 §4。

---

## 0. 定位：不是 fork，不是模板派生

本项目**没有**以 hotspot 为模板搭建。代码结构、模块划分、CLI、扫描器、渲染器都是独立实现的
（`src/` 布局、`scanner` / `todo` / `renderers` / `cli` 分层，见 `docs/architecture.md`）。

对齐的**只有评分语义**：权重、归一化上限、时间衰减与降权系数，使"同一个文件在两个工具里
拿到同一个分数"成为可验证的事实。这样做的理由是可比较性，不是复用实现——目标代码一行未抄，
两个仓库的技术栈（Go / Python）与抽象方式完全不同。

---

## 1. 参考实现与核对快照

| 项目 | 值 |
|---|---|
| 参考实现 | [`huangsam/hotspot`](https://github.com/huangsam/hotspot) |
| 许可 | MIT，© 2025 Samuel Huang（随附 `LICENSE`，1090 字节） |
| 核对所用快照 | 本机 `E:\project\hotspot`，团队账号下的 fork（`liuzhiyang5418/hotspot`） |
| 快照 commit | `97b6d8ab8e9d4814f42a692f86438714ab790682`（2026-08-28，"Update go syntax"） |
| 快照是否被改动 | **无**。`git log origin/main..HEAD` 为空，fork 未产生任何本地提交 |
| 文件级校验 | `core/algo/score.go` 的 blob sha = `fc235c31…`，与上游 `main` 完全相同 |
| 核对的关键文件 | `core/algo/score.go`（371 行）、`schema/data/scoring_config.yaml`（69 行）、`schema/data/presets.yaml`（63 行） |

引用时请引用**上游** `huangsam/hotspot`，fork 只用于固定本次核对的版本。

---

## 2. 完全一致的部分（逐项可核对）

行号分别对应 `score.go`、`scoring_config.yaml`、`presets.yaml` 与
`src/githotmap/core/scoring.py`、`src/githotmap/config/config.py`。

### 2.1 基础模式权重

| 模式 | 指标与权重 | 一致性 |
|---|---|---|
| `hot` | commits .40 / churn .40 / age .10 / contrib .05 / size .05 | ✅ 5 项全同 |
| `risk` | inv_contrib .25 / gini .25 / low_recent .15 / age .15 / size .10 / loc .05 / churn .05 | ✅ 7 项全同 |
| `roi` | churn .35 / loc .25 / gini .25 / age .15 | ✅ 4 项全同 |
| `complexity` | — | ❌ **同名异义，见 §3** |

### 2.2 归一化上限（`score.go:25-32` ↔ `scoring.py:39-54`）

| 指标 | hotspot | githotmap |
|---|---|---|
| contributors | 20 | 20 |
| commits | 500 | 500 |
| size (KB) | 500 | 500 |
| age (days) | 3650 | 3650 |
| churn | 5000 | 5000 |
| recent commits | 50 | 50 |
| LOC | 10000 | 10000 |

### 2.3 归一化公式（`score.go:46-61` ↔ `scoring.py:161-172`）

七项中六项是线性 `clamp(x / cap)`，**`age` 用对数**：

```
n_age = clamp(log1p(age_days) / log1p(3650))
```

我们照搬了对数形式。这一项很容易在移植时被写成线性，两边会立刻产生系统性偏差。

派生量与反转量同样一致：

- `n_inv_contrib = 1 - n_contrib`
- `n_low_recent  = 1 - n_recent_commits`
- `n_gini        = clamp(gini)`（Gini 本身就是 [0,1]）

### 2.4 时间衰减（`score.go:100-103` ↔ `scoring.py:190-195`）

- **只有 `hot` 与 `roi`** 使用衰减后的 commits / churn；`risk`、`complexity` 用原始累计量。
- 半衰期 **180 天**（hotspot 项目文档声明的口径 ↔ `metrics.py:23` `DECAY_HALF_LIFE_DAYS = 180.0`）。
- 衰减形式 `0.5 ** (days_old / half_life)`（`metrics.py:50-55`）。

### 2.5 近因信号（`score.go:63-77` ↔ `scoring.py:125-129`）

```
recency_signal = 0.7 × (recent_commits / commits) + 0.3 × (recent_churn / churn)
```

提交权重高于改动权重，避免单次大规模格式化提交把信号抬满。权重常量两边相同。

### 2.6 降权规则（`score.go:131-148` ↔ `scoring.py:233-239`）

| 触发条件 | hotspot | githotmap |
|---|---|---|
| 路径含 `test` / `generate` / `example` / `mock`，模式为 `risk` | ×0.75 | ×0.75 |
| 同上，其他模式 | ×0.50 | ×0.50 |
| 扩展名属于配置类（yml/yaml/json/toml/cfg/xml/ini/lock/sum/csv/tsv/md/txt/tfstate），模式为 `complexity` | ×0.50 | ×0.50 |

两个条件**独立判定、可以叠加**（一个 `test/config.json` 会被降两次），两边行为一致。

### 2.7 空文件边界（`score.go:20-22` ↔ `scoring.py:148-149`）

`size_bytes == 0` 时直接返回 0 分且分解为空，不参与后续加权。两边相同。

### 2.8 理由生成的模式（`score.go:162-228` ↔ `scoring.py:260-339`）

三条跨指标合成规则与阈值完全移植：

| 模式 | 触发条件（贡献百分比的绝对值） |
|---|---|
| Institutional Amnesia | gini > 20 且 age > 20 且 low_recent > 20 |
| Volatile Anchor | churn > 30 且 loc > 20 |
| Knowledge Silo | gini > 30 或 inv_contrib > 30 |
| 阈值常量 | `significant = 20`、`dominant = 30` |

兜底逻辑（不足 2 条时按 churn / low_recent / loc 补充）与"历史热点 vs 当前瓶颈"的
分支判定（依据 `recency_signal` 对比两个阈值）也一致。

### 2.9 复合模式（`score.go:283-349` ↔ `config.py:52-56`、`scoring.py:435-448`）

| 复合模式 | 配比 | 一致性 |
|---|---|---|
| `active_owners` | hot 50% + risk 50% | ✅ |
| `refactor_now` | complexity 60% + roi 40% | ✅ |
| `legacy_debt` | complexity 70% + risk 30% | ✅ |

权重归一化逻辑也一致：非法或不完整配比时**回退为等权**，合格时按总和归一。
**注意**：`refactor_now` 与 `legacy_debt` 都含 `complexity`，因此它们受 §3 的同名异义影响。

### 2.10 仓库形状预设（`presets.yaml` ↔ `config.py:59-78`）

| 预设 | mode | limit | recency_low | recency_high | 一致性 |
|---|---|---|---|---|---|
| `small` | hot | 10 | 0.10 | 0.40 | ✅ 全同 |
| `large` | roi | 30 | 0.01 | 0.05 | ✅ 全同 |
| `infra` | risk | 20 | 0.05 | 0.20 | ✅ 全同 |

hotspot 的预设还带 `workers` / `precision` / `output` / `color` / `start` / `transitions`
等 CLI 与输出层参数，属于工具外壳而非评分语义，本项目未继承；其中 `start`（时间窗口，
large 为 1 年、infra 为 2 年）在本项目对应 `--since`，默认不限。

---

## 3. 同名异义：`complexity` 模式

这是**唯一**一个模式名相同、语义不同、分数不可直接对比的模式。

| 指标 | hotspot 权重 | githotmap 权重 | 说明 |
|---|---|---|---|
| churn | 0.30 | 0.20 | 共有，权重不同 |
| age | 0.30 | 0.10 | 共有，权重不同 |
| loc | 0.20 | 0.15 | 共有，权重不同 |
| commits | 0.10 | 0.05 | 共有，权重不同 |
| size | 0.05 | — | 我们去掉 |
| low_recent | 0.05 | — | 我们去掉 |
| cc（圈复杂度） | — | 0.20 | **我们新增** |
| nesting（嵌套深度） | — | 0.15 | **我们新增** |
| symbols（符号数） | — | 0.10 | **我们新增** |
| todo_density（SATD 密度） | — | 0.05 | **我们新增** |

两边的侧重不同：

- hotspot 的 `complexity` 是"**大、老、久未动**"——体量与年龄驱动，不含任何静态结构分析。
- 我们的 `complexity` 是"**结构复杂 + 有显式债务标记**"——引入 AST 结构信号与 SATD 密度。

这个差异是刻意的：`docs/nfr.md` 与 `docs/architecture.md` 把 `complexity` 定义为**结构复杂度**，
并明确它不是 AST 圈复杂度的真值（`complexity 40` 是 0–100 相对分）。若要逐字复制 hotspot
的权重，就必须放弃扫描器的结构信号，与本项目的问题定义冲突。

**因此**：若要跨工具比较分数，只能比 `hot` / `risk` / `roi` 三个模式；`complexity` 必须
各自报告且注明口径不同。同理，`refactor_now`、`legacy_debt` 两个复合模式也跨工具不可比。

---

## 4. 有意偏离（我们改了语义，需在报告中说明）

| 改动 | hotspot | githotmap | 理由 |
|---|---|---|---|
| 分解的语义 | `breakdown[key] = weight × norm × 100`，**各项之和 = 分数** | `breakdown[key] = (weight × norm / raw) × 100`，**各项之和恒为 100%** | 降权（§2.6）会让分数偏离 `raw × 100`，hotspot 此时分解之和 ≠ 分数，造成"分解对不上分数"的困惑。改为贡献占比后，分解始终自洽，比例含义也更直观 |
| 权重归一化 | 直接使用配置权重（依赖配置文件本身和为 1） | `_normalize_weights` 额外归一到和为 1 | 允许自定义权重时不手工配平；对默认权重是幂等的，不改变分数 |
| 上限校验 | 无 | 上限非正数时抛 `ValueError` | 防止 `caps` 覆盖成 0 导致除零或静默失分 |
| 复合理由 | 简单拼接各基础模式的理由 | 增加配比 header（`Composite Score: complexity 60% + roi 40%`）与 `[mode]` 前缀 | 让读者知道每条理由来自哪个基础模式 |
| 理由语言 | 英文 | 中文 | 面向中文报告与答辩 |

---

## 5. 我们新增的能力（hotspot 无对应实现）

| 能力 | 位置 | 与本项目 NFR 的关系 |
|---|---|---|
| 风险等级分级（critical/high/medium/low）+ 可配阈值 | `scoring.py:96-111` | 支撑 T2 的"高分"定义与阈值校准 |
| 近因降档：`recency_signal` 低于下限时等级下调一级 | `scoring.py:342` 起 | 防止"历史热点"被当作当前风险 |
| 小样本置信度：提交数 < 3 时标 `low_confidence` | `config.py:112` | 防止低样本文件被当作确定结论 |
| 缺失数据状态：`status = missing`，与"空文件"区分 | `scoring.py:148` 注释与下游 | 支撑 T4「识别数据缺失文件」 |
| 结构信号 5 项与归一化上限 | `scoring.py:174-185`、`DEFAULT_CAPS` 扩展 | §3 的 `complexity` 语义来源 |
| 自适应归一化上限（p90 统计） | `config.py:106` | 大仓库避免大量文件同时饱和 |
| 原因码与降级审计 | `core/diagnostics.py` | **NFR-2** |
| 规范序列化与指纹 | `core/models.py` | **NFR-3**，冻结评估契约的前提 |

这些是工程与可审计性增量，**不是效果优势**——见 §7。

---

## 6. 已知偏差：`imports` 是悬空指标

`scoring.py:178` 计算了 `n_imports`（导入数归一化），`scoring.py:221` 也把它放进了
`complexity` 的归一化集合，但 `config.py:33-42` 的 `DEFAULT_WEIGHTS[COMPLEXITY]` **没有
`IMPORTS` 键**，因此：

1. `weights.get(BreakdownKey.IMPORTS, 0.0)` 恒为 0 → 该信号对分数**零贡献**；
2. `scoring.py:249` 的 `if w > 0` 过滤又使它**不进入 breakdown**；
3. 于是 `_compute_reasoning` 里的 **"Broad Surface"** 理由（要求 `symbols > 20 且 imports > 20`）
   **永远不可能触发**。

影响：不影响任何现有分数与指纹（权重为 0 等价于不存在），但存在一段"算了却从不使用"的
死路径，且它的理由分支永远走不到。

处理选项（**尚未决定，需评审**）：

- **A** 为 `IMPORTS` 补一个非零权重并从其他项匀出——会改变 `complexity` 分数，**会使
  `tests/fixtures/frozen_fingerprints.json` 失效**，必须按 `CONTRIBUTING.md` §5 更新基线；
- **B** 删除 `n_imports` 与 `IMPORTS` 相关的归一化、breakdown 条目与理由分支——零风险，
  但损失一个可能的信号；
- **C** 保留现状并在报告中把它列为已知未启用信号。

> 这一项在 4.5 核对过程中发现，本次只记录，不修改。

---

## 7. 明确不做的对比

- **不做 A/B 效果对比**。我们没有在相同任务上同时运行两个工具并比较结果质量；本项目
  的评估走历史回放（`docs/evaluation-contract.md` §11），与工具间对比无关。
- **不声称"比 hotspot 更好"**。分数接近只说明口径一致，不说明谁更准。
- **不比较分数高低**。两个工具的正常化上限相同，但输入的 Git 历史与文件集合若不同，
  分数本身不可直接并列。
- 可比的只有：**同一仓库、同一时间点、同一种 `hot`/`risk`/`roi` 模式下，两边的分数与排序
  是否一致**。这属于可复现性验证（NFR-3），不是效果评估。

---

## 8. 如何核对本文的说法

```bash
# 1) 确认参考快照未被改动
git -C <hotspot> log --oneline origin/main..HEAD     # 应为空
git -C <hotspot> hash-object core/algo/score.go      # 应为 fc235c31…

# 2) 对照权重
diff <(sed -n '25,33p'  <hotspot>/core/algo/score.go) /dev/null   # 归一化上限
cat <hotspot>/schema/data/scoring_config.yaml                     # 模式权重

# 3) 对照本项目
sed -n '39,54p'   src/githotmap/core/scoring.py    # DEFAULT_CAPS
sed -n '160,240p' src/githotmap/core/scoring.py    # 归一化 / 衰减 / 降权
sed -n '16,78p'   src/githotmap/config/config.py   # 模式权重 / 复合配比 / 预设

# 4) 复算一个文件的分数并比对（同一仓库、同一模式）
python -m githotmap analyze --repo-path <repo> --mode hot --limit 10 --output-file out.json
```

逐项核对的清单就在 §2–§4 的表格里；任何一项对不上，说明两边版本已经漂移。
