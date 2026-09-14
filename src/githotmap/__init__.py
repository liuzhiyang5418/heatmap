"""githotmap —— Git 技术债热力图与优先级排序工具。

该包把 Git 提交历史转化为可量化、可排序、可可视化的技术债信号：

- 采集：单次遍历 ``git log`` 提取每个文件的提交/改动/贡献者元数据；
- 指标：提交数、改动量(churn)、贡献者集中度(Gini)、年龄、大小、近因衰减等；
- 评分：hot / risk / complexity / roi 四种独立评分模式及三种复合模式；
- 排序：按评分降序给出重构优先级；
- 渲染：通过可插拔渲染层输出（默认交互式 HTML 热力图）。

典型用法::

    from githotmap.core.pipeline import AnalysisPipeline

    result = AnalysisPipeline().run(repo_path=".")
    html = result.render("html")
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
