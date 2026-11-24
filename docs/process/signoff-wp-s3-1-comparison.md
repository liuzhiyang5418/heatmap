# WP-S3-1 · 三张对比表（报告素材）

| 项目 | 内容 |
|------|------|
| 用途 | 最终报告「评估」章节的改造前后对比素材 |
| 改造前基线 | `main` @ `daf9500`（Sprint 1 收口，tag `sprint1-final`） |
| 改造后基线 | `main` @ `5ba8b8e`（Sprint 2 收口） |
| 测量环境 | Windows / Python 3.15 / 本机；同一台机器、同一仓库、同一参数 |
| 可信度 | 全部为**实测**，命令见各表下方 |

---

## 表 1 · 健壮性与可审计性（NFR-2）

| 指标 | 改造前 `daf9500` | 改造后 `5ba8b8e` |
|------|------------------|------------------|
| 含中文文件名的仓库：该文件的 `score` | **0.0**（路径被转义 → 与扫描器键交集为空 → `size_bytes=0`） | **0.43**（路径原样，`commits=2`、`loc=1`） |
| 非 ASCII 路径的键形态 | `"\344\270\255\346\226\207..."`（C 风格八进制转义） | `中文模块.py` |
| `degradations_by_code` | `{}`（恒空） | `{'syntax-error': 1}` 等，按 `(path, code)` 去重计数 |
| `--strict --limit 1`（降级文件在 top-1 之外） | 退出码 **0**（静默漏报） | 退出码 **3**，stderr 打印原因码清单 |
| 裸 `except`（`S110` / `BLE001`） | 6 处（pipeline 2 处静默吞掉 + cli 4 处无说明） | **0** |
| 故障注入用例 | 0 | **39 个**（`test_robustness` / `test_git_robustness` / `test_todo_robustness` / `test_analysis_robustness` / `test_nfr2_system`） |
| 覆盖率信息可见性 | 无 | HTML 覆盖率面板（matched / emitted / degraded + 按码计数 + 阶段事件） |
| `ruff check src tests`（全仓） | **27 条** | **0** |
| `mypy src`（全仓） | **18 错 / 7 文件** | **0** |
| 全量测试 | 181 passed / 4 skipped | **286 passed / 8 skipped** |

**关键对照**：改造前的失效是**静默**的——没有异常、没有告警，热力图上该文件只是悄悄变成 0 分。改造后用「原因码贯通 + 覆盖率面板 + `--strict` 退出码」把这类失效变成机器可判定的事件。

复现命令（改造后）：

```powershell
# 建含中文文件名的仓库后
python -m githotmap analyze --repo-path <repo> --mode hot
# 预期：path='中文模块.py'  commits=2  loc=1  score=0.43
python -m githotmap analyze --repo-path <faultyrepo> --strict --limit 1
# 预期：退出码 3，stderr 含 '- syntax-error: 1 处'
```

---

## 表 2 · 可复现性与可验证性（NFR-3）

| 指标 | 改造前 `daf9500` | 改造后 `5ba8b8e` |
|------|------------------|------------------|
| 时间来源分布 | **5 处**散落：`core/models.py`、`scanner/models.py`、`scanner/scanner.py`、`core/metrics.py`、`core/pipeline.py` | **1 处**：`githotmap/clock.py`，其余全部从注入时钟取 |
| 时钟可注入 | 否 | 是（`AnalysisPipeline(clock=)`、`scan_repository(..., clock=)`） |
| 双跑 `analyzed_at` | 每次不同 | `FixedClock` 下**完全相同** |
| 双跑 `age_days` | 随运行日期漂移 | 由注入时刻决定（实测 365.0，换 30 天得 395.0） |
| `canonical()` / `fingerprint()` | 不存在 | 存在；`schema_version = "1.0"` |
| 冻结夹具 | 0 | **3 个**固定快照（固定 `GIT_AUTHOR_DATE` + LF 锁定 + 固定时钟） |
| 跨平台 CI | Ubuntu × 3.10–3.12 | **Ubuntu + Windows** × 3.10–3.12 |
| 「时间来源收敛」的守护 | 无 | `tests/test_clock.py` 全仓检索断言，出现即红灯 |

**关键对照**：改造前「同一仓库跑两次结果不同」是**无法检测**的；改造后既有可注入时钟（能冻结），又有检索断言（防止有人再随手写 `datetime.now()`）。

复现命令（改造后）：

```python
from datetime import datetime, timezone
from githotmap.clock import FixedClock
from githotmap.core.pipeline import AnalysisPipeline

clock = FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
a = AnalysisPipeline(clock=clock).run(repo)
b = AnalysisPipeline(clock=clock).run(repo)
assert a.canonical() == b.canonical()
assert a.fingerprint() == b.fingerprint()
```

---

## 表 3 · 性能（改造前后 + 新特性的代价）

> 本次**不做性能优化**（NFR-1 范围外）。这张表记录的是「为 NFR-2/NFR-3 增加能力」所付出的性能代价，以及瓶颈仍在何处。

| 指标 | 改造前 `daf9500` | 改造后 `5ba8b8e` |
|------|------------------|------------------|
| 分析文件数（本仓库） | 54 | 85（新增 scanner / todo / docs 等模块文件） |
| `analyze` 中位数（3 次） | **2.23 s** | **3.90 s** |
| 折算每文件 | 41.3 ms | **45.9 ms**（+11%） |
| 阶段构成 | git 1.97 s（**88%**）、scanner 0.10 s、todo 0.05 s | git 3692.9 ms（**93.3%**）、scanner 146.8 ms（3.7%）、todo 83.0 ms（2.1%）、metrics 33.5 ms（0.8%）、scoring 3.6 ms（0.1%） |

**结论**：

1. 新增的 scanner + todo 两个阶段合计 **229.8 ms（5.8%）**，这是 NFR-2 可审计性的直接代价，可接受；
2. 每文件耗时只涨 **11%**（41.3 → 45.9 ms），远小于新增的文件数涨幅；
3. **瓶颈仍然是 git 采集（93.3%）**——这正是 NFR-1 的杠杆点（`git log --numstat` 单次遍历 0.264 s vs 逐提交 1.723 s，6.5×），本迭代不做，作为未来工作记录在 `docs/nfr.md` §5。

复现命令（改造后）：

```python
from githotmap.core.pipeline import AnalysisPipeline
r = AnalysisPipeline().run(".", mode="roi", limit=100000)
for stage, ms in sorted(r.stats.stage_elapsed_ms.items(), key=lambda kv: -kv[1]):
    print(stage, round(ms, 1), "ms")
```

---

## 使用说明

- 三张表都可以直接进报告；**表 1 和表 2 是「有/无」对照，表 3 是「代价」说明**，三者不要混用；
- 表 3 的绝对秒数只在同一台机器内可比，跨机器请用「每文件毫秒」或相对倍数；
- 改造前的数字来自 Sprint 1 收口时的实测记录（工作日志），不是估算；
- 若后续做了性能优化（未来工作），需要重测表 3 并注明新的基线日期。
