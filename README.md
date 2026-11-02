# githotmap —— Git 技术债热力图与优先级排序工具

把 Git 提交历史元数据转化为**可量化、可排序、可可视化**的技术债信号，帮助开发团队
"看见"代码库中的风险分布，并据其优先级安排重构与知识传递。

> CS5351 软件工程课程项目（小组选题：Git 技术债热力图与优先级排序工具）。
> 本项目为 Python 实现的**独立 CLI 工具**，核心引擎与渲染/宿主解耦，可插拔扩展。

## 核心思路

不同于传统 linter 或团队速率指标，本工具分析的是**开发行为**：

```
Git 历史
   │  GitPython 遍历提交并读取每次提交的文件统计
   ▼
原始提交记录  ──►  指标聚合（commits / churn / 贡献者 Gini / 年龄 / 大小 / LOC / 近因衰减）
   │
   ▼
评分引擎（4 种模式 + 3 种复合模式，0–100 分 + 分解 + 自然语言理由）
   │
   ▼
优先级排序  ──►  渲染层（默认交互式 HTML 热力图，可插拔替换）
```

## 评分模式

| 模式 | 目标 | 关键信号 |
|------|------|----------|
| `hot` | 活动热点（近期高频改动/波动） | 近期提交、churn、活跃开发 |
| `risk` | 知识风险 / 公交因子 | 贡献者集中、所有权不均、知识孤岛 |
| `complexity` | 技术债候选 | 大、老、维护负担高的文件 |
| `roi` | 重构优先级 | 大文件上的高 churn（技术影响 vs 投入） |

复合模式（融合多维风险）：

| 模式 | 配比 | 适用 |
|------|------|------|
| `active_owners` | hot 50% + risk 50% | 活跃改动且知识孤岛 → 优先知识传递 |
| `refactor_now` | complexity 60% + roi 40% | 冲刺规划 → 按重构回报排序 |
| `legacy_debt` | complexity 70% + risk 30% | 变更前审计 → 脆弱且集中的遗留系统 |

每个文件结果附带 `recency_signal` 与动态阈值，用于区分
**当前活跃热点（Active Frontier）** 与 **历史热点（Historical Hotspot）**，避免把陈旧数据误判为当前风险。

## 快速开始

```bash
# 安装（开发模式）
cd heatmap
pip install -e .

# 安装后也可直接以模块运行
python -m githotmap analyze --repo-path . --mode roi --output html --output-file heatmap.html

# 输出机器可读结果（包含指标、分数分解和状态）
python -m githotmap analyze --repo-path . --mode roi --output json --output-file heatmap.json

# 查看帮助
python -m githotmap --help
python -m githotmap analyze --help
```

生成的 `heatmap.html` 为**自包含交互式热力图**（无外部 CDN，可离线打开）：悬停查看
文件详情与评分理由，点击表头切换排序；色块面积近似反映 LOC，颜色反映当前模式的分数。
灰色表示模型中的 `missing` 状态；目前空文件和缺失文件使用同一个状态，须人工复核。

### 本机 Web 入口

```bash
pip install -e '.[web]'
githotmap serve --port 5000
```

在浏览器打开 `http://127.0.0.1:5000`，输入本机 Git 仓库路径并选择模式。此入口同步调用
现有分析流水线并展示 HTML 报告，只绑定本机；不是托管服务，也没有后台任务、目录筛选或上传功能。
不安装 `web` 可继续使用 CLI 和离线报告。

## 目录结构

```
heatmap/
├── pyproject.toml              # 打包元数据与工具配置
├── README.md
├── src/githotmap/
│   ├── __init__.py             # 版本与公开 API
│   ├── __main__.py             # python -m githotmap 入口
│   ├── cli/main.py             # argparse CLI（analyze / version）
│   ├── core/
│   │   ├── models.py           # 领域模型：枚举、FileMetrics、FileResult、AnalysisResult
│   │   ├── git.py              # Git 采集：单次 log 遍历 + 解析器
│   │   ├── metrics.py          # 指标聚合：Gini、指数衰减、归一化常量
│   │   ├── scoring.py          # 四模式评分 + 复合评分 + 理由生成
│   │   ├── ranking.py          # 优先级排序
│   │   └── pipeline.py         # 采集→指标→评分→排序→渲染 编排
│   ├── renderers/
│   │   ├── base.py             # Renderer 抽象协议
│   │   ├── registry.py         # 渲染器注册表（可插拔）
│   │   └── html.py             # 交互式 HTML 热力图渲染器（默认）
│   ├── config/config.py        # 默认权重 / 阈值 / 预设
│   └── plugins/base.py         # 后续插件扩展协议（预留）
├── tests/                      # 单元测试与样例 fixture
└── examples/demo.py            # 编程式调用示例
```

## 架构与可插拔性

核心引擎（`core/`）**不依赖**任何渲染或宿主，只产出结构化数据
（`AnalysisResult`）。渲染层通过 `renderers.base.Renderer` 协议接入，经
`renderers.registry` 按名称注册/查找。新增输出格式（SVG、终端矩阵、JSON、CSV 等）
只需实现 `Renderer` 并注册，无需改动核心逻辑——这正是"可插拔输出层"的落点。

## 开发

```bash
pip install -e ".[dev]"
pytest                 # 运行测试
ruff check src tests   # 静态检查
mypy src               # 类型检查
```

如需运行浏览器交互测试，设置 `HEATMAP_CHROME` 为本机 Chrome/Chromium 可执行文件路径后再运行
`pytest tests/test_html_browser.py`。该测试需要允许启动独立的无头浏览器。

Sprint 1 的用户故事、架构候选、验收状态和待团队确认事项见 [Sprint 1 记录](docs/sprint-1.md)。


## 研究依据与评价

阶段一资料见 [研究文档入口](docs/research/README.md)：包含六篇论文对照、设计依据、开源工具观察和待执行的评价方案。

当前分数是辅助检查与排序的启发式信号，不等于已确认技术债、缺陷概率、修复工时或真实投资回报。`complexity` 是融合多项信号的评分模式，不等于 AST 圈复杂度。主流水线接入了 TODO 候选数量，但尚未在报告中展示注释原文及位置；扫描或检测失败时仍可能静默回退。论文中的实验效果不代表本项目已经取得同样效果。
