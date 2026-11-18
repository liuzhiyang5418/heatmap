# Git 采集接口（Sprint 2 / Member 4）

`GitHistory.collect_with_degradations(repo_path, since=None)` 返回
`GitCollectResult(records, degradations)`。两类条目均提供 `to_dict()`，仅含 JSON
原生类型。旧接口 `collect()` 仍只返回 `list[CommitRecord]`，会丢弃降级信息。

## 原因码与失败语义

| 场景 | 行为 | code | path |
|---|---|---|---|
| 正常仓库 | 返回文件改动记录，无降级 | — | — |
| 空仓库，无提交 | 空 records，附一条诊断 | `empty-repo` | `None` |
| 浅克隆边界，第一父对象缺失且 diff 失败 | 跳过该提交，保留其他提交记录 | `shallow-clone` | 边界提交完整 SHA |
| 非 Git 目录、其他 Git 失败（含对象损坏） | 抛 `GitError`，`__cause__` 保留原异常 | 不冒充浅克隆 | — |

`GIT_DEGRADATION_CODES` 列出当前取值；公共诊断模型应对齐这些字符串。
`GitDegradation` 包含 `stage="git"`、`code`、`path`、`summary`。
summary 使用固定文本，不包含机器路径或原始异常消息。诊断按 path、code 排序。
非 Git 目录等硬失败由后续流水线统一转为阶段诊断，本接口不会将其伪装为成功。

## 资源与路径

采集和历史分析通过 `_open_repo()` 设置命令级 `core.quotepath=false`，不改写
用户 Git 配置，并在正常返回或异常时关闭 Repo。中文路径以原始路径参与指标聚合。
`since` 裸日期统一为 UTC 零点；merge 提交仍按现有约定排除。

## 与 Member 5 的衔接

分析流水线已使用 `collect_with_degradations()`，将 Git 诊断映射到公共统计、严格模式
与 HTML/JSON 输出。`GitHistory.collect()` 保留为兼容接口，只返回 records；调用方需要
审计信息时应使用 `collect_with_degradations()`。

Member 4 的深度历史分析也提供 `*_with_degradations()` 入口，统一返回结果和空仓库/浅克隆
原因码，`history` CLI 会把限制打印到标准错误。原有 list/值返回接口保留兼容，但遇到空仓库
或浅克隆会发出 `RuntimeWarning`，建议新调用改用可审计入口。

## 验证

`python -m pytest tests/test_git.py tests/test_git_robustness.py tests/test_analysis.py tests/test_analysis_robustness.py`
覆盖中文路径、真实 file:// 浅克隆、空仓库、非仓库、完整及浅仓库非边界 diff
故障、资源释放、深度分析结果的浅克隆诊断、JSON 序列化与同输入双跑一致性。跨平台 CI
由当前 Windows/Linux 工作流验证。
