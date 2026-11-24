# githotmap — 7-minute demo script

| 项目 | 内容 |
|------|------|
| 用途 | CS5351 课程演示（第 12 周，7 分钟） |
| 配套幻灯片 | `githotmap-demo-speech.pptx`（12 页） |
| 目标语速 | 每分钟 125–135 词 |
| 讲稿总词数 | ≈ 900 词 → 实测约 6 分 55 秒，留 5 秒缓冲 |
| 演讲者 | 1 人主讲；如需换人，在第 5 页（Related work）和第 9 页（NFR-3）交接最自然 |

> 用法：幻灯片上只放关键词，**叙述全部在讲稿里**。每页先扫一眼屏幕上的关键词，
> 再按下方 `Say` 段落讲。`Delivery` 是中文提示，不要念出来。

---

## 时间分配

| # | Slide | 秒 | 累计 |
|---|-------|----|------|
| 1 | Title | 10 | 0:10 |
| 2 | The problem | 35 | 0:45 |
| 3 | What we built | 35 | 1:20 |
| 4 | Key idea | 35 | 1:55 |
| 5 | Related work | 30 | 2:25 |
| 6 | Architecture | 30 | 2:55 |
| 7 | **The hard part** | 50 | 3:45 |
| 8 | NFR-2 | 35 | 4:20 |
| 9 | NFR-3 | 35 | 4:55 |
| 10 | Evidence · engineering | 40 | 5:35 |
| 11 | **Evidence · evaluation** | 45 | 6:20 |
| 12 | Takeaways | 30 | 6:50 |

**控场要点**：第 7 页是全场支点，宁可压前面 20 秒也要把它讲完整。第 11 页（评估结果）
是唯一带真实数字的证据页，也不要赶。如果已经超时，第 5 页（Related work）可以只念第一句
和最后一句。

---

## Slide 1 — Title · 10s

**On screen**: project name, one-line positioning (CLI · 4+3 modes · 308 tests · 93% coverage)

**Say**
> Good morning. We built **githotmap** — a tool that turns a Git repository's history into a
> ranked list of files that probably deserve attention. Let me start with the problem that made
> us build it.

**Delivery**：不要念副标题。抬头，语速放稳，最后一句是转场，直接进第 2 页。

---

## Slide 2 — The problem · 40s

**On screen**: `Which files are risky?` + three cards (Today / Linters / Ranked tools) + closing line

**Say**
> Ask any team which files are risky, and you'll get an opinion. Maybe someone remembers a bad
> week. Linters tell you a function is too long — but they don't know that three people rewrote
> that function six times last month. And the tools that do rank files usually hand you a number
> without telling you how much to trust it. So the ranking looks authoritative even when it's
> wrong.
>
> We wanted the opposite: a ranking a team can act on — and check.

**Delivery**：三张卡片依次指一下。最后一句停顿半拍，它是整场的立意。

---

## Slide 3 — What we built · 40s

**On screen**: 4-step pipeline + "one command → one self-contained HTML file"

**Say**
> Here's the pipeline. We read Git history, and aggregate per-file metrics: commits, churn, how
> many people touched the file, how old it is. Those feed a scoring engine with four modes and
> three composite modes. The output is a single HTML file — a heatmap where cell size is lines of
> code and colour is risk, plus a sortable table.
>
> It opens offline. No server, no CDN. One command.

**Delivery**：沿流水线四步走一遍。最后三个短句要断开说，节奏很重要。

---

## Slide 4 — Key idea · 40s

**On screen**: three cards — Behaviour / Auditable / Reproducible

**Say**
> Three choices separate this from a score generator.
>
> First, we score **behaviour, not style**: a file matters because people keep changing it under
> pressure.
>
> Second, it's **auditable** — every file we could not fully analyse carries a machine-readable
> reason code, and the report shows coverage.
>
> Third, it's **reproducible**: the same repository gives the same answer.
>
> Those last two became our two non-functional requirements. They shaped the architecture.

**Delivery**：说 "First / Second / Third" 时各停一下，手指对应卡片。最后一句为第 5、6 页做铺垫。

---

## Slide 5 — Related work · 40s

**On screen**: 3-row comparison table + source footnote

**Say**
> We didn't invent the scoring idea. **hotspot**, a Go tool, normalises and weights signals the
> same way — we aligned our algorithm to it. **CodeCharta** and **CodeCity** show directory
> structure as treemaps; we took the spatial idea but stayed two-dimensional and dependency-free.
> And the SATD literature is clear that TODO comments are evidence, not proof — so we treat them
> as candidates.
>
> What we added on top is the audit trail.

**Delivery**：这是全场最容易超时的一页。只念三个工具名 + 各一句，最后一句收住就进下一
页。不要解释 SATD 是什么，有兴趣的人会在 Q&A 问。

---

## Slide 6 — Architecture · 35s

**On screen**: four layers + three contracts

**Say**
> Architecturally, the core never depends on a renderer. Scanner, TODO detection and Git
> collection feed metrics, scoring and ranking. Three written contracts connect them: the path
> convention, the reason codes, and deterministic output.
>
> That's why a new renderer — or later a new language parser — plugs in without touching the
> scoring engine.

**Delivery**：从上往下指四层，然后用手指划一下第三条契约。"three written contracts" 是这页的唯一卖点。

---

## Slide 7 — The hard part · 55s ★

**On screen**: symptom (red) / root cause / code block / closing warning line

**Say**
> Now the part that taught us the most.
>
> Our worst bug produced **no error at all**. In a repository with a Chinese filename, that file
> scored zero, and the report showed a mangled path. Nothing crashed. Nothing warned.
>
> The cause: Git escapes non-ASCII paths by default — `core.quotepath`. So its key never matched
> the path our scanner read from disk. The two key sets simply didn't intersect. Commits, lines of
> code, score — all zero. And nothing told the user.
>
> That's when we stopped treating robustness as "don't crash". A ranking that is **silently
> wrong** is worse than no ranking — because the team will act on it.

**Delivery**：全场最重要的一页，讲慢一点。说 "Nothing crashed. Nothing warned." 时停顿。
代码块无需逐字念，用手势指出 git side 与 scanner side 的区别即可。最后一句是全场金句，
说完停一秒再翻页。

---

## Slide 8 — NFR-2 · 40s

**On screen**: three mechanisms + "12 fault classes covered"

**Say**
> So NFR-2 became robustness and auditability. Three mechanisms.
>
> One: a **single source** for reason codes — the scanner's enumeration is authoritative, and the
> diagnostics enum references it, so the two can't drift apart.
>
> Two: every pipeline stage is **guarded**. A failure is recorded, not swallowed.
>
> Three: a **strict mode** that exits with code 3 on any degradation — even for a file outside
> the display limit.
>
> Twelve fault classes are covered by tests.

**Delivery**：三条机制念编号，不要念表格细节。最后一句"12 fault classes"是为下一页和证据页留的钩子。

---

## Slide 9 — NFR-3 · 40s

**On screen**: four cards — clock / canonical / snapshots / enforced

**Say**
> NFR-3 is reproducibility, and it's what makes any evaluation possible.
>
> All time sources live in one module, so we can inject a fixed clock. The output is
> canonicalised — clock fields and host identity dropped, keys sorted, floats rounded — and then
> hashed. Three frozen snapshots, with fixed commit dates, must produce the same digest on every
> run, on either operating system.
>
> And a test fails if any module outside the clock calls a time function.

**Delivery**：重点是"这是被强制执行的，不是口号"——最后一句就是证据。

---

## Slide 10 — Evidence · engineering · 40s

**On screen**: 308 / 93% / 12 / 0 + coverage-gate note

**Say**
> What can we prove about the code itself? 308 automated tests pass. Line coverage is 93%, and
> the gate is set at 90%, so it cannot quietly regress. Twelve fault classes are covered, each
> asserting both the reason code and the coverage counts. And the whole repository passes ruff
> and mypy with zero findings — version-pinned, enforced in CI on both Ubuntu and Windows.

**Delivery**：这一页只讲工程证据。最后一句 "enforced in CI" 是过渡，下一页要讲"但这些数字
不能证明排名有用"。

---

## Slide 11 — Evidence · evaluation · 45s ★

**On screen**: 1.95× / 90% / 0.23 + "the set is useful, the ordering is not"

**Say**
> Engineering numbers do not tell us whether the *ranking* is any good. So we evaluated that too,
> by replay: take the tool at the start of an iteration, ask it for the top ten files, then check
> what actually churned in the following weeks. Precision@10 was 90%, against a 46% chance
> baseline — a lift of 1.95×.
>
> Two caveats, both on the slide. Recall was only 50%, and the rank correlation was 0.23. The set
> is useful; the ordering inside it is not. And a shorter window returned 0.94× — we report that
> as a failure rather than dropping it.

**Delivery**：全场唯一带真实评估数据的页面，也最容易被追问。说 "1.95×" 要清楚，说 "the
ordering is not" 要坦然——主动承认比被问出来好得多。

---

## Slide 12 — Takeaways · 30s

**On screen**: three takeaways + command line

**Say**
> To sum up. githotmap answers "where should we look first?" with a ranking you can check. Two
> non-functional requirements — auditability and reproducibility — were carried through the
> architecture, not bolted on. And the hardest lesson: the dangerous bugs raise nothing at all.
>
> The one thing still open is the participant study. Thank you — happy to take questions.

**Delivery**：最后一句前停一下。如果时间到了 7 分钟，直接说 "Thank you" 收尾，不要补内容。

---

## 预案

### 如果被要求加演示（+1 分钟）
在第 3 页后插入现场演示，60 秒内完成：
1. `python -m githotmap analyze --repo-path . --mode roi --output-file demo.html`
2. 打开 demo.html，悬停一个色块展示评分理由
3. 指着覆盖率面板说 "these are the files we could not fully analyse — with reasons"

### 如果只给 5 分钟
删掉第 5 页（Related work）和第 9 页（NFR-3），讲稿相应改为：
"Related work and reproducibility details are in the report; the core contribution is the audit
trail." 这样仍在 5 分钟内落到第 12 页（评估页务必保留）。

### Q&A 高频问题与应答

| 问题 | 应答要点 |
|---|---|
| 分数等于技术债吗？ | 不等于。是待验证的候选信号；`complexity` 也不等于 AST 圈复杂度。 |
| 做过用户实验吗？ | **Q2 做了**：历史回放，Lift 1.95×（90% vs 46% 基线）。Q3（界面可用性）**明确放弃**，契约里写明"dropped, not executed"。 |
| Precision 90% 是不是说明很准？ | 不是"准确率"。它是对 30 个可比文件的命中重叠，基线已有 46%，所以真正有意义的是 **1.95× 的提升**。 |
| 排名可靠吗？ | **排序不可靠**：Recall@10 只有 50%，Spearman ρ 0.23。我们只主张"集合有用"，不主张"顺序正确"。 |
| 有失败的结果吗？ | 有。短窗口跑出 0.94×，我们**照实报告**，没有删掉——它反而说明了方法的前提条件。 |
| 和 hotspot 有什么不同？ | 算法同源；我们加了原因码审计链与冻结指纹，并且修了它同样存在的 quotepath 盲点。 |
| 为什么不支持其他语言？ | 契约层是语言无关的，但解析器要逐个实现。属未来工作，不影响本迭代的两个 NFR。 |
| 性能如何？ | 3000 文件约 14.7 秒，瓶颈已定位在 GitPython 逐提交读取（numstat 单次遍历快 6.5 倍），性能优化明确列为本迭代范围外。 |
