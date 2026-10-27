# 独立对抗性审查

独立 Luna 仅阅读题面、输入域及候选源码，不读取既有测试和通过结论。主控按需求依据裁决；原监视器保持不变。

提出 1 项假设；确认 0 项；待处理 1 项。

每条可执行轨迹在全新进程中重放两次。数值断言采用既有相对/绝对 1e-9 容差。

| ID | 任务 | 假设 | 执行裁决 |
|---|---|---|---|
| ADV-001 | moving_average | Trigger rising edge during reset is consumed | needs_requirement_clarification |

原始提案、需求裁决、两次逐扫描执行及源码哈希分别留档。没有确认反例不代表正确性证明；题面歧义不计入代码缺陷。

执行后端：STruC++ 0.7.0 + g++；未运行 CODESYS、形式化验证或实体 PLC。
