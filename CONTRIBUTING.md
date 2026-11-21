# Contributing

面向本仓库的开发者与维护者。内容包括本地环境、测试分层、质量门禁、提交规范，
以及**这个项目特有的坑**——后者多数是真实踩过并修过的，写在前面能省别人一次排查。

---

## 1. 环境

| 项 | 说明 |
|---|---|
| Python | **3.10+**（CI 覆盖 3.10 / 3.11 / 3.12；本地另验过 3.15） |
| 运行时依赖 | `GitPython>=3.1` |
| 可选依赖 | `[web]` → Flask（仅 `githotmap serve` 需要） |
| 开发依赖 | `[dev]` → pytest / pytest-cov / ruff / mypy |

```bash
git clone https://github.com/liuzhiyang5418/heatmap.git
cd heatmap
pip install -e '.[dev,web]'
```

> 不安装也能跑测试：`tests/conftest.py` 会把 `src/` 加入 `sys.path`。
> 但 `pip install -e .` 会顺带验证打包配置，建议装上。

---

## 2. 测试分层

| 命令 | 范围 | 何时用 |
|---|---|---|
| `pytest` | 全部（含 `slow`） | **提交前**，约 2 分钟 |
| `pytest -m "not slow"` | 排除性能用例 | 快速反馈，约 100 秒（CI 主 step 用它） |
| `pytest -m slow` | 性能回归守卫 | 改了 pipeline / scanner / metrics 之后 |
| `pytest --cov` | 覆盖率，阈值 **90%** | 改了核心模块之后 |

性能用例标了 `slow` 是刻意的：它们测的是**与机器无关的相对量**（4 倍文件数 → 耗时不超 8 倍），
在 6 个 CI 组合上各跑一遍没有意义，所以只在 Linux/3.11 跑。

### 测试文件的分工（加新用例前请先看这里）

| 文件 | 职责 |
|---|---|
| `test_cli_smoke.py` | 命令行参数 → 流水线 → 渲染 → 写盘 → 退出码，这条真实路径 |
| `test_cli_diagnostics.py` | `--verbose` / `--report-coverage` / 原因码处置建议 |
| `test_robustness.py` | 12 类故障注入（NFR-2.1） |
| `test_scanner_codes.py` | 扫描原因码的取值、结构与覆盖（NFR-2.2） |
| `test_diagnostics_consistency.py` | 原因码唯一来源 + 降级计数不丢不重 |
| `test_determinism.py` / `test_frozen_fingerprints.py` / `test_clock.py` | NFR-3 三个层次 |
| `test_performance.py` | 性能回归守卫（WP-S3-2.2） |

避免重复：渲染器本身的用例在 `test_html.py` / `test_json_renderer.py`，
CLI 端到端在 `test_cli_smoke.py`，两者不要互相越界。

---

## 3. 质量门禁（CI 会拦下）

| 检查 | 阈值/版本 | 说明 |
|---|---|---|
| `ruff check src tests` | **0 告警**，锁定 `0.17.5` | 全仓，不是"变更的文件" |
| `mypy src` | **0 错误**，锁定 `2.4.1`，`strict = true` | 同上 |
| 覆盖率 | **≥ 90%**（实测 92.9%） | `[tool.coverage.report] fail_under` |
| `pytest` | 全绿 | ubuntu + windows × Python 3.10–3.12 |

**ruff / mypy 为什么锁版本**：`pyproject.toml` 没有显式 `select`，告警集合取决于
ruff 版本的默认规则集。不锁版本，升级一次 ruff 就可能冒出几百条新告警。

**覆盖率阈值为什么是 90% 而不是 70%**：先测出真实值（92.79%）再定的，留 3% 缓冲。
**不要为了达到某个数字去凑测试**——门禁的作用是防退化，不是达标。

---

## 4. 提交规范

Conventional Commits，描述用中文：

```
feat(cli): 新增 --verbose 与 --report-coverage
fix(pipeline): 降级计数按 (path, code) 去重
test(nfr3): 冻结指纹基线，实现真正的跨平台断言
docs(nfr): 记录跨平台指纹一致的实证
chore(quality): ruff / mypy 全仓归零
```

- 标题一行说清做了什么；正文解释**为什么**，以及**取舍**（放弃的方案是什么、为什么放弃）。
- 涉及口径变更（故障类清单、strict 语义、指纹规范）必须在正文说明，并回填 `docs/nfr.md` §7。
- 一个 PR 做一件事；合并前确保 CI 绿。

---

## 5. 这个项目特有的坑（请务必读）

这些都是真实踩过并修过的，不是假设。

### 5.1 不要在业务代码里取时间

```python
# ✗ 会让结果随运行日期漂移，冻结指纹永远对不上
now = datetime.now(timezone.utc)
elapsed = time.perf_counter()

# ✓ 从注入的时钟取
from githotmap.clock import SystemClock
clock = SystemClock()
now = clock.now()
elapsed = clock.monotonic()
```

`tests/test_clock.py::test_time_sources_are_confined_to_clock_module` 会全仓检索
`datetime.now(` / `time.perf_counter(` / `time.time(`，**只允许出现在 `githotmap/clock.py`**。

### 5.2 夹具写文件必须显式 `newline="\n"`

```python
# ✗ Windows 上会写成 \r\n，size_bytes 变化 → 指纹与 Linux 不同
path.write_text(content, encoding="utf-8")

# ✓
path.write_text(content, encoding="utf-8", newline="\n")
```

这个坑让团队在 Sprint 2 误以为"跨平台摘要天然不成立"，把契约弱化了一轮；
Sprint 3 找到真因后才恢复成"两平台摘要相同"。详见 `docs/nfr.md` §3.3 的 D4 note。

### 5.3 测试里建仓库必须自带 git 身份

```python
# ✗ 依赖运行机器的全局 git 配置，CI 上会因 "Committer identity unknown" 失败
repo.git.commit("-m", "msg")

# ✓
subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-m", "msg"], cwd=repo, check=True)
```

注意：`git merge` **不接受** `-c user.*` 之外的写法，必须在临时仓库里写局部配置
（见 `tests/test_git.py` 的 `repo.config_writer()` 用法）。

### 5.4 `git.Repo(...)` 用完要 close

GitPython 的 `Repo` 会惰性持有 `git cat-file --batch` 子进程。不 close 会泄漏进程与文件句柄，
Windows 上还会导致临时目录删不掉。用 `with git.Repo(path) as repo:` 或 `try/finally`。

### 5.5 更新冻结指纹前先想清楚

`tests/fixtures/frozen_fingerprints.json` 是两个平台共同断言的基线。改动它等于改变
NFR-3 的验收口径，必须：

1. 确认是**有意的**格式变更（例如去掉了某个非确定字段）；
2. 同时提升 `AnalysisResult.schema_version`；
3. 在提交信息里写明原因与影响。

如果只是为了让某个平台变绿就去改基线，那是在掩盖平台相关缺陷。

### 5.6 仓库属主与 git 的 `dubious ownership`

如果克隆来的仓库属主与当前用户不同，git 会拒绝操作：

```powershell
# 单次生效，不改动全局配置
git -c safe.directory=<repo-path> status
```

在 CI 上不存在这个问题；本机换机器/换用户时才遇到。

---

## 6. 提 PR 之前

- [ ] `pytest` 全绿（或至少 `pytest -m "not slow"`）
- [ ] `ruff check src tests` 无告警
- [ ] `mypy src` 无错误
- [ ] 若改了核心模块，`pytest --cov` 覆盖率仍 ≥ 90%
- [ ] 若改了原因码、strict 语义、指纹规范，已回填 `docs/nfr.md` §7
- [ ] 提交信息说明了"为什么"，不只是"做了什么"

契约与架构见 [`docs/architecture.md`](docs/architecture.md)；NFR 口径见 [`docs/nfr.md`](docs/nfr.md)。
