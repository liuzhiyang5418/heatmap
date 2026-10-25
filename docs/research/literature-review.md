# 技术债研究依据与文献对照

本调研用于界定 githotmap 的技术债候选信号和可视化评价边界。P1–P4 为核心依据，P5–P6 为分类与改进方向的补充。下述工程建议不表示已被论文验证；未复现实验。

## 范围与定义

依据 P1，技术债可理解为过去的软件技术决策或实现方式留下、从当前视角看会妨碍未来演化或增加维护负担的内部问题。环境变化也可能使原本合理的选择变成负担。技术债不等于工具能检测到的全部问题；质量指标不能直接决定偿还顺序，还要考虑未来变化、成本、价值和依赖。

githotmap 的当前分数用于辅助定位维护热点和检查优先级，不是已确认债务数量、缺陷概率或修复工时。是否值得偿还需要人工结合源码与业务背景判断。

## 论文对照

| 编号 | 研究问题 | 数据与方法 | 可借鉴内容 | 局限与证据位置 |
|---|---|---|---|---|
| P1 | 如何界定技术债及其管理？ | 概念讨论；技术债 landscape 和未来成本/价值权衡，无预测数据集 | 项目范围、候选信号与真实债务的区别 | 不验证评分算法；IEEE Software pp.18–21，Fig.1–2 |
| P2 | SATD 有多少、为何引入、是否移除？ | Eclipse、ArgoUML、Chromium OS、Apache httpd；人工阅读 101,762 条注释，归纳 62 个模式 | 注释原文、位置、命中理由与人工复核 | Java/C/C++ 语料，不代表 Python；注释可过时；作者版 PDF pp.3–4 §III、pp.8–10 §V–VI |
| P3 | 相对 churn 能否预测缺陷密度？ | Windows Server 2003→SP1；2,465 binaries、96,189 文件；绝对/相对指标回归比较与留出验证 | 区分次数、变更行数和规模/时间归一化 | binary 粒度的缺陷预测，不是技术债评分；PDF pp.2–3 §3–4、pp.5–8 §5 |
| P4 | CodeCity 是否改善理解任务？ | FindBugs、Azureus；正式 45 人中分析 41 人；组间设计；CodeCity 对比 Eclipse＋Excel | 公平基线、总览与精确任务、正确性和耗时 | 排除一项不公平任务及四位参与者；三维类级结果不能外推文件级二维图；PDF pp.3–10 §4–10 |
| P5 | 技术债与管理研究如何分类？ | 系统映射 1992–2013 年 94 篇研究；10 类债务、8 项活动、29 工具 | 区分识别、度量、排序、表示、沟通、监控、偿还和预防 | 历史范围，不代表最新全貌；不同研究对缺陷债定义有冲突；§4.4–4.5、Table 4/7 |
| P6 | NLP 能否改善设计/需求 SATD 识别？ | 10 个 Java 项目，62,566 条人工分类注释；最大熵分类器，留一项目验证；固定模式和随机基线 | 积累标签，再评估规则与文本分类 | 非 Python/中文验证；F1 不是准确率；作者版 §2.5、§3-RQ1、Table 2 |

## SATD：关键词是候选入口

P2 的 62 个模式包含 hack、fixme 等，但不等于只数 TODO。其报告的 2.4%–31.0% 是含候选项的文件比例，不是检测准确率（Table III）。删除注释不保证偿还债务；代码变化后旧注释也可能失效（§V）。其复杂性代理为依赖/Fan-in，不能转述成“圈复杂度与债务无关”。

以下为自拟示例，不是论文实验样本：

| 示例 | 初步判断 | 风险 |
|---|---|---|
| `# TODO: replace this duplicated parser after release` | 债务候选 | 需核对重复实现是否仍存在 |
| `# TODO: add dark mode next semester` | 普通需求待办 | 未承认当前内部实现不足 |
| `# No workaround is needed after upgrading` | 排除或复核 | 关键词忽略否定语义会误报 |
| `# Keep workaround until upstream issue 42 is fixed` | 候选并记录外部依赖 | 合理兼容措施未必应立即删除 |
| `message = "FIXME: sample"` | 非注释 | 全文件关键词扫描会误报 |
| `# This assumes only one tenant` | 需上下文 | 不含关键词，可能漏检；取决于实际需求 |

未来接入建议：词法区分注释、字符串与代码；Docstring 单列来源；按注释块去重；保存路径、行号、原文、上下文、规则和复核状态。人工标签需同时覆盖命中与未命中注释，才能估计召回率。

## Churn：原文与当前实现的口径

P3 的 Churned LOC 是新增＋修改行，Deleted LOC 单列；Lines worked on 为二者之和。其八个相对指标分别为：Churned LOC/Total LOC、Deleted LOC/Total LOC、Files churned/File count、Churn count/Files churned、Weeks of churn/File count、Lines worked on/Weeks of churn、Churned LOC/Deleted LOC、Lines worked on/Churn count（§3–4）。

Weeks of churn 是版本控制记录的累计编辑时长，不等于日历窗口或有提交的周数。当前仓库的 churn 是逐提交新增＋删除行数；不能称为完整复现 P3。替换一行通常产生一删一增；累加 diff 不等于首尾快照的一次 diff。

同一窗口内的自拟例子：

| 文件 | 提交数 | 新增＋删除 | 末态 LOC | 变更/LOC | 每提交变更行 |
|---|---:|---:|---:|---:|---:|
| A.py | 20 | 100 | 100 | 1.00 | 5 |
| B.py | 2 | 500 | 2,000 | 0.25 | 250 |

A 更频繁、相对自身规模更活跃；B 总量和单次改动更大，不能据此断言哪一个真实债务更多。相对指标若后续采用，应明确 LOC 口径、零分母、小文件偏差、删除文件和缺失历史的处理。

P3 §5.2 中绝对与相对模型拟合 R² 为 0.052 与 0.811；拟合优度不是预测准确率，更不能用于宣称当前加权分数已被验证。

## 可视化与改进方向

P4 的基线允许用 Excel 排序，不是刻意弱化的表格。平均正确性评分从 4.803 到 5.968，时间从 41.048 到 36.117 分钟（Table 7）；这是该实验中约 +24% 和 −12% 的相对变化，不是本项目结果。A4.2 因需要未训练的定制能力而被排除；精确查找任务中地图未必优于表格。评价应同时包含总览和精确任务，并预先规定排除规则。

P5 记录不同研究对“缺陷是否属于债务”的冲突。本文采用 P1 的内部负担视角，普通新功能待办不自动计债。P5 §4.5.1 一处写 nine，但摘要及 Table 7 列出八项管理活动，此处采用实际列表。

P6 Table 2 中设计债平均 F1 为 NLP 0.620、模式 0.267；需求债为 0.403、0.067。后续应先积累人工标签、检查跨项目泄漏，再考虑分类器；不能直接承诺 Python/中文语料达到同样效果。文本与静态 smell 的文件级共现，也不等于二者确认了同一债务。

这些论文没有共同验证本仓库的评分权重、贡献者集中度解释或 ROI 收益。相关评分仍是待验证的工程启发式。

## 参考文献与公开来源

- **P1** Philippe Kruchten, Robert L. Nord, Ipek Ozkaya. Technical Debt: From Metaphor to Theory and Practice. IEEE Software, 2012, 29(6):18–21. [SEI](https://insights.sei.cmu.edu/library/technical-debt-from-metaphor-to-theory-and-practice/)
- **P2** Aniket Potdar, Emad Shihab. An Exploratory Study on Self-Admitted Technical Debt. ICSME, 2014. [DOI](https://doi.org/10.1109/ICSME.2014.31) · [作者版](https://users.encs.concordia.ca/~eshihab/pubs/Potdar_ICSME2014.pdf)
- **P3** Nachiappan Nagappan, Thomas Ball. Use of Relative Code Churn Measures to Predict System Defect Density. ICSE, 2005. [Microsoft Research 全文](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icse05churn.pdf)
- **P4** Richard Wettel, Michele Lanza, Romain Robbes. Software Systems as Cities: A Controlled Experiment. ICSE, 2011:551–560. [DOI](https://doi.org/10.1145/1985793.1985868) · [作者版](https://wettel.github.io/download/Wettel11a-icse.pdf)
- **P5** Zengyang Li, Paris Avgeriou, Peng Liang. A systematic mapping study on technical debt and its management. Journal of Systems and Software, 101, 2015:193–220. [DOI](https://doi.org/10.1016/j.jss.2014.12.027) · [大学存档](https://research.rug.nl/en/publications/a-systematic-mapping-study-on-technical-debt-and-its-management/)
- **P6** Everton da S. Maldonado, Emad Shihab, Nikolaos Tsantalis. Using Natural Language Processing to Automatically Detect Self-Admitted Technical Debt. IEEE TSE, 43(11), 2017:1044–1062. [DOI](https://doi.org/10.1109/TSE.2017.2654244) · [作者版](https://das.encs.concordia.ca/pdf/Maldonado_TSE2017.pdf)

核读日期：2026-09-20。页序按对应公开作者版 PDF；P6 作者稿有 2016 占位页眉，正式出版年份为 2017。文中为重点阅读摘要，不是全文翻译。
