# 对抗性审查环节

流程为：Luna 作者生成 ST → 普通编译及场景测试 → 独立 Luna 阅读题面和源码 → 提出带输入轨迹和输出断言的假设 → 格式/源码哈希检查 → 需求依据裁决 → 两次新进程执行复核 → 经确认的失败反馈作者 → 原测试和审查轨迹一起回归。

独立审查者不拿已有测试、参考实现、监视器或通过结论。代码作者与审查者均按用户要求使用 GPT-6 Luna 的不同上下文。主控负责工具、需求裁决和证据整理。模型调用目前由本次子代理编排完成，MCP 工具本身不会自动调用模型。

## 提案与需求裁决分开

提案采用 `plc-probe-review-v1`。`candidates` 保存每份源码的绝对路径和 SHA256；`findings` 保存问题依据、假设及完整输入序列。每行格式为 `{"time_ms": 0, "inputs": {…}}`，每个断言只含扫描序号、输出名和期望字面量，不接受表达式或可执行代码。输入沿用已有有限支持域。

需求裁决另存为 `plc-probe-adjudication-v1`：

```json
{
  "schema": "plc-probe-adjudication-v1",
  "decisions": [
    {"id": "ADV-001", "decision": "ambiguous", "reason": "原题未规定该交互的优先级"}
  ]
}
```

`accept_requirement` 表示期望值可由题面明确推出；`accept_contract` 表示仅在已声明测试契约下成立；`ambiguous` 留待需求澄清；`reject` 表示主张缺乏依据。裁决文件是主控审阅记录，不是模型自行认可的真值，更不是用户批准或形式化证明。

## 执行裁决

- 提案格式、输入域或源码哈希不符：拒绝执行，不计为程序缺陷。
- 无独立需求裁决：`pending_adjudication`，不能算通过。
- 题面有歧义：`needs_requirement_clarification`，即使输出与提案不同也不确认缺陷。
- 与冻结监视器的期望不一致，或该输出未被监视器评分：`oracle_disagreement`，需复核判据。
- 有依据、与监视器一致的断言在两次新进程中都失败：`confirmed_requirement_violation` 或 `confirmed_contract_violation`。
- 有依据的假设经执行满足断言：`not_reproduced`，保留被反驳意见。
- 编译/运行失败、两次结果不稳定：单独记录，不能冒充逻辑反例。

每条轨迹从新 FB 开始，两次复核各启动新进程。浮点断言沿用现有相对/绝对 `1e-9` 容差。不能直接删减带固定期望数值的审查轨迹，因为删去历史输入可能改变正确答案；当前保存完整轨迹。普通监视器反例仍使用原有精简工具。

## 运行与接入

```powershell
python -B -m plc_probe review experiments/adversarial_review/round_1/proposals_v2.json --adjudication experiments/adversarial_review/round_1/adjudication.json
python -B -m plc_probe.model_evaluation repair_2 --review-proposals experiments/adversarial_review/round_1/proposals_v2.json --review-adjudication experiments/adversarial_review/round_1/adjudication.json
```

第二条会先跑原有三类测试，再执行审查，合并记录在 `experiments/luna/results/repair_2_with_review.*`，不覆盖原评估。审查候选必须属于所评估生成阶段。

MCP 增加 `plc_adversarial_review`：必填 `proposals_path`，可选 `adjudication_path`、`output`。完整结果、两次执行、断言、原监视器判据及构建日志分别存盘。默认报告为提案目录内的 `evaluation.json` 和 `evaluation.md`。

CLI 状态 `fail` 表示确认反例；`needs_review` 表示仍有歧义、判据冲突或工具问题，两者退出码均为 1。`no_confirmed_counterexample` 退出码为 0，只表示本轮没有确认反例。

本地执行仍是 STruC++ + g++，不等同于 CODESYS 编译、形式化验证或工业设备验证。
