# githotmap —— Git 技术债热力图与优先级排序工具

把 Git 提交历史元数据转化为**可量化、可排序、可可视化**的技术债信号，帮助开发团队
"看见"代码库中的风险分布，并据其优先级安排重构与知识传递。

> CS5351 软件工程课程项目（小组选题：Git 技术债热力图与优先级排序工具）。
> 本项目为 Python 实现的**独立 CLI 工具**，核心引擎与渲染/宿主解耦，可插拔扩展。

## 核心思路

不同于传统 linter 或团队速率指标，本工具分析的是**开发行为**：

```
Git 历史
   │  单次遍历 git log（numstat + 作者 + 时间）
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

# 或直接以模块运行（无需安装）
python -m githotmap analyze --repo-path . --mode roi --output html --output-file heatmap.html

# 查看帮助
python -m githotmap --help
python -m githotmap analyze --help
```

生成的 `heatmap.html` 为**自包含交互式热力图**（无外部 CDN，可离线打开）：悬停查看
文件详情与评分理由，点击表头切换排序，色块大小映射复杂度、颜色映射风险等级。

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


## 研究依据与评价

阶段一资料见 [研究文档入口](docs/research/README.md)：包含六篇论文对照、设计依据、开源工具观察和待执行的评价方案。

当前分数是辅助检查与排序的启发式信号，不等于已确认技术债、缺陷概率、修复工时或真实投资回报。`complexity` 评分模式也不等于 AST 圈复杂度；SATD 注释证据尚未接入主流水线。论文中的实验效果不代表本项目已经取得同样效果。
