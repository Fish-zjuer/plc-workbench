# TIA 最终验收结果

基线：`integration-20261103@ea42b6e`。本目录只保存最终验收结论、对应源码和必要的原生输出；重放不调用作者模型。

| 验收项 | 最终结果 |
| --- | --- |
| PUBLIC_08 默认完整流程 | 4 个场景、320 次调用、640 项共享断言通过；4 个驱动均 0 错误、0 警告 |
| PUBLIC_08 有界形式化 | 相同 boundary 域、bound=3、unwind=16；4/4 形状、8/8 性质通过 |
| PUBLIC_08 负对照 | 4 个场景均正确检出原始数组被修改，形式化门禁阻止后续执行 |
| 基线 ST / TIA SCL 对照 | 15/15 组一致：7 个正例、8 个预期反例 |
| 实际 TIA 编译 | 8/8 份 SCL 接受，0 错误 |
| 自动回归 | 81 项通过 |

SHL 正负例各有 1 条符号/精度转换告警，循环计数范围固定为 0..31；其余六份移植源码无告警。所有原生测试实例均已关机、注销。

## 原生行为覆盖

| 题目 | 场景 | 采样 | 断言 |
| --- | --- | --- | --- |
| CUSTOM_01 | 7 | 186 | 2784 |
| PUBLIC_03 | 3 | 114 | 452 |
| PUBLIC_07 | 1 | 80 | 1200 |
| PUBLIC_17 | 3 | 64 | 1457 |
| PUBLIC_05 | 1 | 9 | 12 |
| CUSTOM_09 | 25 | 48 | 192 |

行为表仅表示冻结有限测试通过；CUSTOM_09 另有 bound=20、10 条性质有界通过。

## 形式化对照

| 用例 | 基线 ST | TIA SCL | 上界 |
| --- | --- | --- | --- |
| alias | bounded_pass | bounded_pass | 3 |
| alias_mutant | counterexample | counterexample | 3 |
| return | bounded_pass | bounded_pass | 3 |
| pv1 | bounded_pass | bounded_pass | 3 |
| pv1_mutant | counterexample | counterexample | 3 |
| pv1_bounds | bounded_pass | bounded_pass | 3 |
| 08_correct | bounded_pass | bounded_pass | 3 |
| 08_raw_write | counterexample | counterexample | 3 |
| 08_config_write | counterexample | counterexample | 3 |
| 18_correct | bounded_pass | bounded_pass | 4 |
| 18_count_only | counterexample | counterexample | 4 |
| 18_missing_read | counterexample | counterexample | 4 |
| 18_wrong_empty_status | counterexample | counterexample | 4 |
| shift | bounded_pass | bounded_pass | 3 |
| shift_mutant | counterexample | counterexample | 3 |

ST/SCL 每对使用同一任务快照、原规约、输入域、调用方存储契约、扫描周期、上界和资源限制。引用模型、观察器、判卷器及求解核心保持基线原样。PUBLIC_18/PV1 对照仅覆盖基线的本地存储契约，不是原生 VARIANT ABI 验收。以上是明确输入域与有限扫描范围内的结论。

## 文件与复现

- `report.json`：机器可读汇总。
- `pairs/`：基线 ST、对应 SCL 与最终结果。
- `tasks/`：去重后的形式化规约快照；课程行为输入引用已冻结的 `datasets/course32.json`。
- `native/`：默认开放数组正负对照源码、最终输出与执行结果。
- `behavior/`：已通过的原生行为源码与结果。
- `files.sha256.json`：本目录其他文件的校验和。

配置、适配边界与复现命令统一见 [TIA 使用说明](../../docs/TIA_VERIFICATION.md)。
