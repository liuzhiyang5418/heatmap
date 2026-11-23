# Evaluation toolkit

三个脚本，对应 `docs/evaluation-contract.md` 的执行阶段。契约本身是冻结的，这里只提供
**执行手段**——不改变任务、指标或阈值。

| 脚本 | 作用 | 何时用 |
|---|---|---|
| `build_answer_key.py` | 从**固定快照**算出 T1/T2/T4 的答案键，并给出 T3 的候选与指标明细 | 招募参与者**之前**，一次 |
| `run_pilot.py` | 逐题引导参与者、计时、记录答卷（匿名） | 每次会话 |
| `score_responses.py` | 按契约 §5 给答卷打分并汇总 | 会话结束后 |

---

## 0. 前置：把快照钉死

答案键必须绑定**具体提交**，否则参与者看到的数据与你算答案用的数据不是同一份：

```bash
git -C <repo> rev-parse HEAD          # 记下这个 sha
```

`build_answer_key.py` 会把 `repo_head` 写进答案键。若该字段为空（非 Git 目录），
说明快照不可复现，不要用它做正式评估。

---

## 1. 生成答案键

```bash
python examples/evaluation/build_answer_key.py \
    --repo <快照路径> --data X --mode roi \
    --out answer_key_X.json
```

产出内容（节选）：

```jsonc
{
  "repo_head": "ac54bbd...",          // 快照绑定
  "T1": {"rule": "score desc, path asc", "answer": [ {...}, {...}, {...} ]},
  "T2": {"rule": "high/total desc, directory asc", "answer": {...}},
  "T3": {"candidates": [ ... ]},      // 解释题候选，答案需人工撰写
  "T4": {"rule": "status == missing", "answer": [ ... ]}
}
```

**T3 是唯一需要人工的一题**：从 `--show-t3-candidates` 里挑一个文件，写出「引用哪两项指标、
为什么它属于候选而非确诊」的标准答案，记进答案键的 `T3.expected` 字段后再分发。

```bash
python examples/evaluation/build_answer_key.py --repo . --data X --show-t3-candidates
```

> **T2 的「高分」怎么定义**：答案键用**该数据集分数的第 75 百分位**作阈值（top 25%），
> 而不是 `severity ≥ high`。原因是后者依赖绝对阈值（75/50），小仓库上可能一个文件都够不到
> ——实测本仓库 `roi` 模式最高分仅 24.99，T2 会变成无解。分位数定义随数据集自适应，
> 实际阈值会写进答案键的 `high_score_threshold`，口径因此仍然冻结。

---

## 2. 跑试点

契约 §6 要求**先导 2 人**检查说明、难度与时限。流程：

```bash
# 1) 先生成参与者要看的报表（数据 X，与答案键同一快照、同一模式）
python -m githotmap analyze --repo-path <快照路径> --mode roi --output-file report_X.html

# 2) 打开报表，然后跑引导脚本
python examples/evaluation/run_pilot.py \
    --participant P01 --data X --report report_X.html --out-dir responses
```

每题默认 180 秒时限；超时**不中断**，只在答卷里标 `over_limit`，由评分脚本单独报告
（契约 §5 要求失败与超时单列，不能只统计成功者）。

### 组内成员参与 pilot 的规矩

- **pilot 可以用组内成员**——契约 §6 本来就要求先导 2 人。
- **正式数据不建议**：组内成员知道实现与预期结果，存在利益冲突。
- 若最终只能用组内样本，**必须在报告中披露**「便利样本、参与者来自团队内部」，
  并说明这不构成独立用户验证。
- 同一人不要同时参与 X 与 Y 两个数据集，否则学习效应会污染设计。

---

## 3. 打分

```bash
python examples/evaluation/score_responses.py \
    --key answer_key_X.json --responses responses/ --out scores_X.json
```

输出示例：

```
参与者  数据     T1   T2   T3*  T4   总计   耗时(s)  超时
P01     X         3    2    2    1    8/9     412.3  -
P02     X         2    1    1    1    5/9     538.0  T2,T3
* T3 为自动粗筛结果，契约要求人工复核后再入表。
```

**T3 必须人工复核**：脚本只检查「是否出现两项指标关键词」和「是否有候选≠确诊的表述」，
无法判断推理是否正确。

---

## 4. 报告时不要做的事

契约 §7 已经冻结，这里再强调三条最容易犯的：

| 不要 | 为什么 |
|---|---|
| 只报成功完成的会话 | 超时与放弃必须单列，否则完成率被高估 |
| 看到地图表现差就删掉那道题 | 事后删题等于改目标 |
| 把 T1 得分当成「评分准确」的证据 | 它只证明参与者读对了排序，不证明排序本身有意义 |

---

## 5. 数据最小化

- 答卷只含：匿名 ID、数据集标识、各题答案、耗时、是否超时。
- **不要**采集姓名、邮箱、IP、设备信息、浏览器指纹。
- 公开报告使用匿名 ID；原始答卷不入库（`responses/` 建议加进 `.gitignore`）。
