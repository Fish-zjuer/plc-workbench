# PLC 工具原型：第一轮实测

运行时间：2026-10-26T19:57:22.317163+08:00。固定种子：20261026。

## 这轮做了什么

实际编译并执行 ST 源码。后端是 STruC++ 0.7.0 和 g++；输出由独立手写的逐扫描契约检查器判断。
覆盖作业中的电机启停示例、公共题 06 风机延时启动、公共题 02 DWORD 边沿检测。

样本是人工构造的正确实现与故意植入错误的实现，**不是模型生成效果、工业现场故障统计或完整作业实验**。

## 实测计数

- 编译成功：18 / 18。
- 正确对照：6 个；出现测试失败的对照：0 个。
- 人工故障样本：12 个。
- 正常路径检出：4 个。
- 针对性场景检出：12 个。
- 固定种子随机场景检出：12 个。
- 已精简并在新进程复现的反例：12 个。
- 实际执行扫描总数：86908；本次运行耗时 43.469 秒（受构建缓存影响）。

正常路径、针对性和随机套件的场景数不同；这轮只能说明具体场景能否揭露这些人工故障，不能归因于生成策略优劣或宣称公平预算下更高效。

## 样本结果

| 任务/实现 | 样本性质 | 正常路径 | 针对性场景 | 随机场景 | 精简反例 |
|---|---|---|---|---|---|
| motor/correct | 正确对照 | 0 / 1 失败 | 0 / 512 失败 | 0 / 40 失败 | — |
| motor/alternative | 正确对照 | 0 / 1 失败 | 0 / 512 失败 | 0 / 40 失败 | — |
| motor/lost_latch | 人工故障 | 1 / 1 失败 | 16 / 512 失败 | 30 / 40 失败 | [4 → 2 轮](counterexamples/motor__lost_latch.json) |
| motor/start_over_stop | 人工故障 | 0 / 1 失败 | 387 / 512 失败 | 40 / 40 失败 | [4 → 1 轮](counterexamples/motor__start_over_stop.json) |
| motor/ignore_estop | 人工故障 | 0 / 1 失败 | 184 / 512 失败 | 40 / 40 失败 | [4 → 1 轮](counterexamples/motor__ignore_estop.json) |
| blower/correct | 正确对照 | 0 / 1 失败 | 0 / 37 失败 | 0 / 40 失败 | — |
| blower/alternative | 正确对照 | 0 / 1 失败 | 0 / 37 失败 | 0 / 40 失败 | — |
| blower/timer_not_reset | 人工故障 | 0 / 1 失败 | 32 / 37 失败 | 28 / 40 失败 | [6 → 3 轮](counterexamples/blower__timer_not_reset.json) |
| blower/timer_ignores_demand | 人工故障 | 0 / 1 失败 | 17 / 37 失败 | 12 / 40 失败 | [6 → 2 轮](counterexamples/blower__timer_ignores_demand.json) |
| blower/ignore_estop | 人工故障 | 0 / 1 失败 | 16 / 37 失败 | 19 / 40 失败 | [6 → 2 轮](counterexamples/blower__ignore_estop.json) |
| blower/count_each_scan | 人工故障 | 1 / 1 失败 | 35 / 37 失败 | 9 / 40 失败 | [8 → 3 轮](counterexamples/blower__count_each_scan.json) |
| blower/early_delay | 人工故障 | 1 / 1 失败 | 37 / 37 失败 | 18 / 40 失败 | [6 → 2 轮](counterexamples/blower__early_delay.json) |
| edges/correct | 正确对照 | 0 / 1 失败 | 0 / 35 失败 | 0 / 40 失败 | — |
| edges/alternative | 正确对照 | 0 / 1 失败 | 0 / 35 失败 | 0 / 40 失败 | — |
| edges/count_only_16_bits | 人工故障 | 0 / 1 失败 | 19 / 35 失败 | 40 / 40 失败 | [2 → 2 轮](counterexamples/edges__count_only_16_bits.json) |
| edges/missing_falling_count | 人工故障 | 0 / 1 失败 | 35 / 35 失败 | 40 / 40 失败 | [4 → 2 轮](counterexamples/edges__missing_falling_count.json) |
| edges/latched_changed_flag | 人工故障 | 0 / 1 失败 | 33 / 35 失败 | 40 / 40 失败 | [3 → 2 轮](counterexamples/edges__latched_changed_flag.json) |
| edges/previous_updated_early | 人工故障 | 1 / 1 失败 | 35 / 35 失败 | 40 / 40 失败 | [2 → 2 轮](counterexamples/edges__previous_updated_early.json) |

## 相同扫描调用预算的后续比较

每个实现分别使用 12、48、192 次 FB 调用，10 个固定种子。下表是每轮检出的人工故障个数（共 12 个）的均值。
只对齐调用数，没有对齐虚拟时间跨度、复位次数或实际耗时；针对性场景与人工故障也并非独立工业数据。

| 每个实现的扫描预算 | 策略 | 平均检出 / 12 | 最少—最多 |
|---|---|---|---|
| 12 | 针对性 | 9.1 | 5—11 |
| 12 | 随机 | 5.7 | 5—6 |
| 48 | 针对性 | 10.7 | 10—12 |
| 48 | 随机 | 7.4 | 6—10 |
| 192 | 针对性 | 12 | 12—12 |
| 192 | 随机 | 10.7 | 8—12 |

## 初步结论及边界

1. 先观察正常运行不足以评价这些有状态程序：中断、重复输入和高位边界能揭露额外错误。
2. 反例可保存为带绝对采样时间的输入序列，缩短后重放；它适合作为 agent 修复反馈及回归用例。
3. 目前没有运行 CODESYS 编译、PLCVerif、实体 PLC 或任何基座模型；没有完成四组作业实验。
4. 当前只支持三个固定接口契约。任意 ST 程序可以交给后端编译，但没有契约就无法自动判断行为正确。
5. 计时以虚拟时间为准；输出取本轮执行后值。输入在相邻采样点之间保持不变。没有测试多任务抢占、实际 I/O 或重启持久化。
6. 边沿检测题没有定义首轮历史值，首轮只建立观测历史，不判正确性。没有替题目补充隐含要求。
7. 对照均通过不是通用误报率证明；人工故障检出率也不能外推到工业现场。还需要第三方实现、独立盲测和真实问题案例。
8. 下一步优先接 CODESYS 执行后端，对同一反例交叉重放；再测试真实 agent 输出，而非继续增加自造故障。

## 可追溯文件

- `results.json`：源代码 SHA256、每个场景结论、构建日志位置、环境。
- `counterexamples/*.json`：精简输入、逐轮实际/预期输出、违反的性质及重放状态。
- `../../examples/manifest.json`：人工故障定义及全部 ST 源码位置。
- `../../docs/CONTRACTS.md`：扫描语义、时间约定、规约与假设。
