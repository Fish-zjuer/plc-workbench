# TIA 对 integration-20261103 已有能力的适配

本轮基线固定为 `ea42b6ebcd41228d7c3e41ee526a9aafa9550751`。只验收基线已经具备且能由真实工具复现的能力，不扩展或重写共享形式化模型。题库、判据、PLCverif/CBMC、引用模型和观察器保持基线原样。

## 适配修改

- 原生开放数组测试按独立场景分批构建虚拟卡，每个场景保留全部行、原始边界及独立调用方存储。全部批次成功后汇总原生输出，由原全题判据统一判定。没有抽样或切断单个场景的状态。所有批次共用既有预算和绝对截止时间；失败、超时、协议错误和环境变化不能成为通过。
- `LOWER_BOUND/UPPER_BOUND` 的 `ARR`、`DIM` 命名参数及维度 1 的整数类型字面量，转换为共享模型接受的位置参数。支持命名参数换序，保留原数组参数；动态维度、其他维度、缺参或歧义参数明确拒绝。
- Siemens POU 的起始 `BEGIN` 是包装标记。临时变量生命周期处理完成后移除该标记，避免共享引用模型在 `REPEAT` 内展开出非法的嵌套 `BEGIN`。不删除其他语句或候选的提前 `RETURN`。

## 形式化对照

`scripts/check_tia_baseline.py` 读取固定 Git 提交中的参考源码，生成对应 SCL，并在两端调用相同共享模型。每对使用相同的任务快照、原公式、输入假设、类型/尺寸、扫描周期、扫描上界、展开上限、时间和内存限制。源文件、转换后的模型、配置及逐性质状态分别保存。

- 引用/别名/RETURN：来自基线 `scripts/check_plcverif_references.py`，bound=3、unwind=8、timeout=45s。
- PUBLIC_08：来自基线 `examples/formal/Q08.st` 和 `scripts/check_course_references.py`，4 种数组形状，boundary 数值域、bound=3、unwind=16、timeout=180s。保留正确程序、原始数组写坏、配置字段写坏三例。
- PUBLIC_18：来自相同基线的 Q18/PV1 回归，4 种载荷类型 × 容量 1/2/7，bound=4、unwind=16、timeout=180s。这是本地 PV1 存储契约的源模型检查，不是 TIA 原生 VARIANT ABI 验收。
- SHL：复用基线测试中 `SHL(DWORD#1, bitIndex)`、计数 0..31 的受限模式，加上可观察的位校验输出及负例；bound=3、unwind=256、timeout=120s。共享移位实现保持原样。

运行已由真实基线检查确认的 15 组对照：

```powershell
python scripts/check_tia_baseline.py --output outputs/tia_baseline_pairs_new --ids alias,alias_mutant,return,pv1,pv1_mutant,pv1_bounds,08_correct,08_raw_write,08_config_write,18_correct,18_count_only,18_missing_read,18_wrong_empty_status,shift,shift_mutant
```

独立检查其中有原生厂商接口的 SCL 是否能被实际 TIA 编译：

```powershell
python scripts/check_tia_baseline.py --output outputs/tia_baseline_compile_new --compile-only outputs/tia_baseline_pairs_new --ids alias,alias_mutant,return,08_correct,08_raw_write,08_config_write,shift,shift_mutant
```

## 本机验收结果（2026-11-04）

- PUBLIC_08 默认正例：实际编译通过，四个完整原生场景共 320 次调用、640 项共享判据断言通过，四个驱动均 0 错误、0 警告。随后在基线 boundary 域、bound=3 下，4/4 形状和 8/8 性质有界通过。
- 原始数组写坏的负例：默认流程仍完整执行 320 次调用，四个场景均检出错误，形式化按门禁记为 not_executed。
- 15/15 组 ST/SCL 形式化对照一致；其中 7 个正例、8 个预期反例。对应的 8 份原生接口 SCL 均被实际 TIA 编译接受，0 错误；SHL 正负例各保留 1 条符号/精度转换告警，循环计数范围固定为 0..31。
- 81 项相关自动回归通过，新增作者模型调用为 0；共享验证核心没有改动。

本机完整证据位于 `reports/tia_final_20261104/README.md`，包含源码、参数、逐性质结果、原生输出和散列清单。

## 结论范围

本轮仅验收真实基线检查已确认的 15 组能力。额外的继承模型探测需显式传入 `--include-probes`，不计入最终已验收清单。PV1 对照只覆盖其本地存储契约。

所有结果限定于列明的类型、数组尺寸、数值域与扫描范围，不宣称整个题库、全部浮点输入或厂商全语义等价。
