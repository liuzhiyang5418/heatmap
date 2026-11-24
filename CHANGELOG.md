# Changelog

本项目按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 组织，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。`0.2.0` 之前的版本号从未单独发布过，
`0.1.0` 对应 Sprint 1 收口（git tag `sprint1-final`，commit `daf9500`）。

## [0.2.0] — 2026-11-23

Sprint 2 与 Sprint 3 的交付合并为本次版本：两项非功能需求落地、代码质量基线归零、
评估契约冻结并执行。

### 新增 — NFR-2 健壮性与可审计性

- 单一原因码来源：`scanner.Limitation` 为权威词表，`core.diagnostics.DegradationCode`
  引用其值而非复制字面量（D1）。
- 流水线阶段守卫：每个阶段记录 `stage-failed` 与耗时，禁止裸 `except: pass`（D3）。
- 双策略：默认尽力而为并记录降级；`--strict` 下任一降级以退出码 3 终止（D2）。
- 降级按 `(path, code)` 去重计数，避免 scanner 与 TODO 重复标记同一文件（D4）。
- 覆盖率可见：`files_matched` / `files_emitted` / `files_degraded` 与逐码计数进入 HTML 与 JSON。
- 11 个原因码各自带可执行的处置建议，经 `--verbose` 与报告详情暴露。
- 12 类故障注入测试（非 ASCII 路径、二进制、超大、语法错误、声明编码、符号链接、
  空仓库、非 Git 目录、浅克隆、不可读、深层嵌套、损坏对象）。

### 新增 — NFR-3 可复现性与可验证性

- 可注入时钟 `clock.py`（`SystemClock` / `FixedClock`），位于包顶层以避免 `core` 循环导入；
  仓库内 `datetime.now` / `perf_counter` / `time.time` 调用收敛为 0 处。
- `AnalysisResult.canonical()` 规范序列化 + SHA-256 `fingerprint()`，`schema_version` 可追溯。
- 3 个冻结合成快照与提交基线 `tests/fixtures/frozen_fingerprints.json`。
- 跨平台两级契约：夹具级两平台**摘要相同**（CI 6 组合同一基线）、外部仓库级自洽与
  检出路经无关。

### 新增 — 工程与调试支持

- 覆盖率门禁 `fail_under = 90`，实测 92.91%（1952/2101）。
- 性能回归守卫（相对度量，与机器无关）。
- CLI 端到端冒烟测试（HTML / JSON / strict）。
- `--verbose`：阶段耗时与逐条降级明细；`--report-coverage`：导出 `AnalysisStats` 为 JSON。
- `CONTRIBUTING.md`（开发/测试/提交规范与已知陷阱）与 `docs/architecture.md`
  契约索引（每条不变量由哪份文档定义、哪个测试守护）。

### 新增 — 评估

- 冻结评估契约 `docs/evaluation-contract.md`（v1.0，2026-11-20）。
- 契约升 v1.1：Q2 由**历史回放**回答，Q3（参与者研究）标注为放弃、未回答。
- 历史回放脚本 `examples/evaluation/historical_replay.py`：在 `t0` 打分，统计窗口内真实
  改动，输出 Precision / 随机基线 / Lift / Recall / Spearman，含样本量护栏。
- 结果归档 `docs/evaluation-replay-result.md`：主窗口 Lift 1.95×，敏感性窗口 0.94× 一并报告。
- 参考实现对照 `docs/research/reference-alignment.md`，README 与 `THIRD_PARTY_NOTICES.md`
  声明评分语义来源。

### 修复

- **M4-2（P0）**：非 ASCII 路径下 `core.quotepath` 使全部历史指标静默归零——修正路径解析
  并补回归测试。
- `--strict` 原先只检查 `--limit` 内的文件，漏掉窗口外的降级。
- `degradations_by_code` 恒为空，降级计数从未真正生效。
- M5-1：breakdown 改为加权贡献百分比，各项之和恒为 100%，与分数解耦。
- 7 处 GitPython `Repo` 未关闭导致的资源泄漏。
- Windows 上 `write_text` 写出 CRLF 导致 `size_bytes` 与指纹跨平台不一致——夹具统一
  `newline="\n"`。

### 变更

- `complexity` 模式改用 AST 结构信号与 SATD 密度，与参考实现的同名模式语义不同，
  分数不可跨工具比较。
- 版本号 `0.1.0` → `0.2.0`。

## [0.1.0] — 2026-11-07

Sprint 1 收口（git tag `sprint1-final`，commit `daf9500`）。

### 新增

- 四种基础评分模式（`hot` / `risk` / `complexity` / `roi`）与三种复合模式
  （`active_owners` / `refactor_now` / `legacy_debt`），分数 0–100 并带分解与理由。
- Git 历史采集（GitPython）与指标聚合：提交数、churn、贡献者 Gini、年龄、大小、LOC、
  近因衰减。
- 扫描器（AST 结构）与 TODO/FIXME/HACK/XXX 检测。
- 自包含交互式 HTML 报告与 JSON 输出；可选 Flask 本地入口（仅回环）。
- CLI（`analyze` / `history` / `serve`）与退出码契约（0/1/2/3）。
- CI 测试矩阵与 Sprint 1 验收记录 `docs/sprint-1.md`。

[0.2.0]: https://github.com/liuzhiyang5418/heatmap/compare/sprint1-final...sprint3-final
[0.1.0]: https://github.com/liuzhiyang5418/heatmap/releases/tag/sprint1-final
