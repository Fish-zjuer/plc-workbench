# 在现有 CODESYS 工作流中接入 TIA

本次只增加平台适配。SHL、TON、开放数组、VARIANT、CBMC 性能与验证窗口问题由队友维护的共享验证后端负责，此分支不再另行修复或替换它们。

## 共用与替换的边界

| 共用部分 | TIA 替换部分 |
| --- | --- |
| 题库、需求、接口和测试判据 | SCL 作者提示、固定接口检查 |
| Trial：6 个版本、24 次请求、1800 秒预算、请求计量 | `.scl` 文件与 TIA 评估入口 |
| self / Codex、两个模型、批量并发、暂停/恢复/停止 | 平台选择及 TIA 环境检查 |
| 测试序列和 `dataset.judge_output` | Openness 编译、PLCSIM Advanced 仿真执行 |
| `dataset_formal.attach`、PLCverif、CBMC、LTL 结果处理 | SCL 语法正规化回调，随后调用原共享验证器 |
| 日志、历史、版本、CSV、统计与最终代码导出 | 平台字段与 `.scl` 下载 |

TIA 的单题入口、CLI 完整检查及 2×2 批量实验均使用现有 Trial/Campaign。CODESYS 的现有入口及默认行为保留。模型请求可以并行，单机 TIA 调用串行排队，防止同时启动大量 Portal 会话。

完整流程为：生成源码 → 厂商编译 → 原生测试 → 共用判卷 → 共用形式化入口 → 结果记录/预算内修复。编译与行为阶段未通过时，形式化不执行，与 CODESYS 相同。遇到共享后端不支持、超时或待复核反例时，保留它的结论，不另外造一个 TIA 验证模型让其通过。

`tia_formal.py` 仅处理 SCL 边界：块名与局部变量写法、头部元数据、定时器实例调用写法、移位函数命名参数，以及 Siemens 临时变量的调用生命周期。开放数组边界查询的 `ARR := a, DIM := UDINT#1` 转为共享前端的 `a, 1`，不改变数组上下界；动态或非一维查询明确拒绝。POU 起始 `BEGIN` 在临时变量初始化建模后移除，避免进入引用调用展开体。它不提供 SHL/SHR 或 TON 的函数实现，不修改共享验证上界、求解策略、输入域或 LTL 判据。类型与指令是否支持最终由共享后端决定。

多场景开放数组默认逐个完整场景编译和执行，避免将所有形状展开到一个超过 CPU 代码容量的驱动中。每个场景原本就使用独立实例及调用方存储；批次不截短输入，不拆分单个状态轨迹。全部原生行按原顺序汇总后，只调用一次冻结的全题判据。各批次共用原仿真总时间预算和绝对截止时间；源码、运行器或输出协议变化、缺少任一批次均不能计为通过。`simulation/batch_manifest.json` 记录形状、行偏移、输入场景散列及各批次证据。基线对照的范围与复现见 [TIA 基线兼容性](TIA_BASELINE_COMPATIBILITY.md)。

## 本机配置与使用

1. 构建 `integrations/tia_bridge/TiaBridge.csproj`，使用本机 Openness V21 的 `net48` API 目录。构建会同时生成独立的 `TiaRuntime.exe`，部署时与 Bridge 放在同一目录；仅编译不需要启动该运行器。
2. 在“模型与环境”填写 Bridge、编译模板及可选 Openness 目录。
3. 原生仿真还需要已授权的 PLCSIM Advanced x64 API DLL，以及专用 S7-1500 `.ap21` 仿真模板。当前 S7-1200 模板仅用于编译。新 EXE 的 Openness 访问确认由使用者手动处理。
4. 形式化工具继续使用共用的 `formal_config.json`。本机已解压的 PLCverif/Java/CBMC 位于忽略目录 `.runtime`，不随代码提交。

Bridge 默认创建无界面 TIA 会话，结束时通过 Dispose 关闭自身创建的 Portal。需要交互演示或诊断时，可设置 `TIA_BRIDGE_WITH_UI=1`；图形模式断开连接后会保留界面，使用者需关闭已完成的会话。

原生执行分为两个进程：`TiaBridge.exe` 完成工程编译与虚拟卡导出并关闭 TIA，随后启动不引用 `Siemens.Engineering` 的 `TiaRuntime.exe`，由它负责 PLCSIM 注册、上电、执行、采样与清理。`prepared_card.json` 绑定源码、组合测试驱动、Bridge、运行器及虚拟卡文件哈希；运行器拒绝不匹配的交接，Python 在结束时再次检查运行环境是否变化。该隔离便于诊断，不能单凭进程拆分声称上电稳定性已经解决。

原生实例按仿真模板 CPU 的实际订货号注册，上电最多等待 180 秒。试用许可剩余天数提示需确认；可手动点击 OK，或按 [试用通知辅助工具](TIA_TRIAL_ACK.md) 单独启动有时间和次数限制的监听器。这与 Openness 访问授权不同。上电前、成功后及失败时的状态、许可、CPU 类型和耗时记录在 `simulator_runtime.json`，不会把启动超时当作候选逻辑错误交给模型修复。原生执行仍需保留启动、工程准备及测试的总时间预算。

```powershell
# 现有 SCL，使用相同阶段门禁检查；不调用模型
python -m plc_agent tia check PUBLIC_02 path/to/candidate.scl --output outputs/tia_check

# 通过共用 Trial 生成、检查与修复
python -m plc_agent tia run PUBLIC_02

# 保留阶段三单独编译模式
python -m plc_agent tia run PUBLIC_02 --compile-only
```

工作台单题选择 TIA；批量实验也可选择 TIA，复用原有 self/Codex × 模型 A/B 的四组实验。平台配置未齐全时预检查阻止付费批量生成。

## 最终验证结果

[最终验收报告](../reports/tia_final_20261104/README.md)汇总原生行为、形式化对照、源码及必要执行结果。PUBLIC_08 默认分批流程完整执行 4 个场景、320 次调用、640 项共享断言，驱动 0 错误、0 警告；随后按基线 boundary 域和 bound=3 完成 4 种数组形状、8 条性质的有界检查。原始数组写坏的负例被四个原生场景检出，后续形式化按门禁阻断。

15 组基线 ST/SCL 正负例的逐性质结果一致；8 份对应 SCL 均被实际 TIA 编译接受。已有电梯、REAL 报警、泵组、配方、TON 与状态机的原生行为结果也集中在最终报告。81 项相关回归检查通过。

共享 PLCverif/CBMC、LTL、引用模型、观察器及判据保持基线原样。形式化只对报告列明的输入域与扫描范围有效，PV1 源模型不代表厂商原生 VARIANT ABI。适配层支持集合见 [语义边界](TIA_ADAPTER_HARDENING.md)，运行环境见 [环境说明](TIA_NATIVE_ENVIRONMENT.md)。
