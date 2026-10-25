# 开源工具对照与界面观察

调研日期：2026-09-20。CodeCharta 官方在线样例经过实际浏览和交互；其他项目核对官方 README，未安装或运行。以下为工程建议，不以项目宣传或星数验证效果。

| 项目 | 功能 | 借鉴内容 | 引入建议与原因 |
|---|---|---|---|
| [CodeCharta](https://github.com/MaibornWolff/codecharta) | 分析与三维文件地图展示分离，多指标编码 | 目录搜索、指标说明、图例 | 借鉴交互；不引入整套三维系统 |
| [code-maat](https://github.com/adamtornhill/code-maat) | revisions、churn、coupling 等历史分析 | 区分频率、行变更与共同变更 | 文献/实现参考；当前已有 Git 模块，不增加重复依赖 |
| [churnmap](https://github.com/Meru143/churnmap) | 文件共同变更矩阵、关系图、表格和 JSON | 文件对关系及报告结构 | 扩展参考；不是单文件风险评分器 |
| [Radon](https://github.com/rubik/radon) | Python 圈复杂度、规模、Halstead、可维护性指数 | 静态指标定义及对照 | 当前已有 scanner；先比较口径，不直接替换或重复接入 |
| [PyDriller](https://github.com/ishepard/pydriller) | Git commits、modified files、diffs | 历史分析 API | 当前已有 GitPython；无明确缺口时不叠加 |
| [Apache ECharts](https://github.com/apache/echarts) | 交互图表和 Treemap | 层级布局、提示和点击事件 | 可选扩展；当前 HTML 无 CDN，选用前评估离线打包与体积 |

## CodeCharta 实际观察

[官方样例](https://codecharta.com/visualization/app/index.html?file=codecharta_visualization.cc.json.gz&file=codecharta_analysis.cc.json.gz&currentFilesAreSampleFiles=true) 页脚版本为 v2.5.0，使用其自带分析与可视化项目数据，没有上传仓库源码。

| 操作 | 观察 | 对 githotmap 的启发 |
|---|---|---|
| 搜索 `fileValidator.ts` 后回车，再清除 | 显示文件从约 2.5K 变为 1，清除后恢复 | 路径过滤、结果数及清除操作应可见 |
| 展开 Legend | 面积、高度、颜色分别解释；示例颜色区间为 0–60、61–121、122–184 | 图例说明指标和阈值，不移植样例阈值作为债务阈值 |
| 打开颜色指标菜单 | 指标可搜索，有文字说明；本轮未切换指标 | 保留定义与来源，避免同名复杂度混用 |
| 查看 Explorer 状态 | 显示 2,533 visible，394 with no area in current metric | 零规模/无面积条目须仍能在表格查找 |

最有用的三点是路径搜索与清除、可展开图例、带定义的指标菜单。目录下钻和注释证据面板是拟扩展设计，本轮未声称逐项实测。

## 两种“热力图”的区别

文件地图中每块代表一个文件，适合观察风险/规模分布；共同变更矩阵的行列都是文件，每格代表文件对的共变关系。后者不能直接替代当前文件评分。共同变更还可能由正常协作或批量提交造成，不自动证明架构缺陷。

正式引入任何依赖时再固定版本、核对 LICENSE 和打包方式；本次调研不新增运行时依赖。
