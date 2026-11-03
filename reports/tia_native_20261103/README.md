# TIA 原生行为与共享形式化验收（2026-11-03）

CUSTOM_09 的既有模型生成 SCL 连续两次完整通过。模型修复版在使用者终端复验中也完成真实原生行为与共享有界形式化；此前的上电和 TIA 安全访问超时保留，不从结果中删除。

随后由 Agent 使用相同源码再做两轮完整复测，均通过。独立运行器三轮上电耗时分别为 9.188、8.128、12.128 秒；每轮新建自有仿真实例，25 场景、48 采样、192 断言全通过，10/10 共享形式化在 20 扫描上界内通过，均完成关机与注销。三轮没有额外模型请求。

| 记录 | 新增模型请求 | TIA 编译 | 原生行为 | 共享形式化 |
| --- | ---: | --- | --- | --- |
| model-rerun-1 | 0 | 0 错误、4 警告 | 25 场景、48 采样、192 断言，0 失败 | 10/10 bounded_pass，上界 20 |
| model-rerun-2 | 0 | 0 错误、4 警告 | 同上，0 失败 | 同上 |
| model-repair / version_1 | 0 | 通过 | 192 断言中检出 5 项失败 | 按行为门禁不执行 |
| model-repair / version_2 | 1 | 0 错误、0 警告 | PowerOn 初始化约 63 秒超时，未采样 | 不执行 |
| model-repair-recheck | 0 | 通过 | PowerOn 约 63 秒超时，使用者未看到试用窗口 | 不执行 |
| model-repair-isolated-recheck | 0 | 通过 | 同一 Bridge EXE 的 API 子进程上电仍超时 | 不执行 |
| model-repair-runtime-host-recheck | 0 | TIA 安全访问初始化超时，未开始编译 | 未启动 | 不执行 |
| manual-runtime-host-20261103-195607 | 0 | 0 错误、0 警告 | 25 场景、48 采样、192 断言，0 失败 | 10/10 bounded_pass，上界 20 |
| model-repair-runtime-repeat-1 | 0 | 0 错误、0 警告 | 同上，0 失败 | 同上 |
| model-repair-runtime-repeat-2 | 0 | 0 错误、0 警告 | 同上，0 失败 | 同上 |

两次重跑复用先前由 `deepseek-v4.1-flash-1017` 生成的同一份代码，SHA256 为 `0f8d72243d08fc9424d1243e7defb76503fc16961283b69b08df44364e5424de`；此前生成调用为 1 次，本轮未重复生成或人工修改源码。

自动修复实验的种子是助手构造的已知错误代码。原生判卷先真实检出 5 项失败，随后模型根据反馈生成修复版，SHA256 为 `34b89c353ce7145fc470d67f034fc553d6304dadf71b5de9b362d3be5ddd3321`。修复版没有人工修改；环境超时后停止，没有让模型继续修改代码。使用者从自己的终端发起同源码复验，119.656 秒完成全部阶段，新增模型请求为 0。该结果验收了模型修复后的代码；由于中间存在环境中断和人工发起复验，不将其描述为单次全自动闭环自行恢复。

## 上电与会话

新版 Bridge 默认使用无界面 TIA，结束后自身创建的 Portal 自动退出；按模板的 19 字符实际订货号注册 CPU 1511，取代通用 CPU 实例；保留 180 秒固件等待参数，并记录启动前后和失败时的运行状态。重复清理已注销实例正常结束。

两次完整重跑的上电耗时为 9.368 秒和 9.128 秒。另有三个 API 诊断实验：前两次启动并完成模型代码测试驱动，第三次超时；这些失败保留在 [startup-probes.json](startup-probes.json)，不从统计中删除。

后续独立 PowerShell 和 C# API 宿主可在 26.008 秒、63.196 秒启动同一修复版虚拟卡并完成驱动，见 `additional-startup-probes/`；没有采集完整输出，因此不计为行为通过。独立形式化预检查为修复版 10/10 bounded_pass，上界 20，见 [辅助预检查](repair-formal-precheck.json)，也不代替完整 Trial。新增 `TiaRuntime.exe` 不引用 Openness；使用者终端的完整复验上电 9.188 秒，读取 48 行实际输出并完成判卷与形式化，最后关机、注销成功。运行时记录 `openness_assemblies_loaded=false`。三项真实交接负例均在加载 API 前拒绝执行。

西门子试用许可提示有独立确认期限，未及时确认会导致实例不启动；增大 PowerOn 固件等待参数不能代替该确认。出现提示时需要使用者手动处理，没有通过 Computer Use 操作，也未更改许可证设置。没有逐轮记录窗口是否出现、是否点击，因此当前结果不表示试用模式可以完全无人值守，不能保证所有冷启动均已稳定。官方说明：[Trial License](https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced/installing/introduction/trial-license?contentId=xlNJOAPK2cqXCzika8BSFQ)。

使用者明确确认：手动终端成功轮次只点击了 PLCSIM 试用提示，没有重新允许 Openness。后续两轮由 Agent 发起，窗口交互未单独记录。三轮成功说明当前环境下新建实例的有限重复性；没有测试 Windows 重启、所有负载或长期无人值守。

## 证据与边界

- [机器可读摘要](report.json)，各目录保存源码版本、厂商编译诊断、实际输出、上电状态、实例清理及形式化摘要。
- [文件哈希清单](files.sha256.json)。完整工程、虚拟卡、原始大体积日志继续留在忽略的 `.tmp-tests/tia-stable-rerun-20261103/`。
- 仿真为 PLCSIM Advanced V8 试用模式；模板为 CPU 1511-1 PN / V2.9，保留 CPU 访问密码，专用离线模板的配置数据加密明确设为 None。受保护配置密码下装仍是限制。
- 只有一个简单题的有限测试和 20 扫描有界形式化，不是无界证明、实体 PLC 验证或全部题型覆盖。未修改共享 CBMC/PLCverif 的模型或算法。
- Bridge 与运行器构建 0 错误、0 警告；26 项 TIA 回归测试通过。此前 2026-11-01 的 64 个交付文件哈希未变化。用户在部分历史超时轮次明确反馈未看到试用窗口，不能仅凭 Timeout 认定未点击确认；历史根因尚未完全定位，三轮成功不等于覆盖所有启动条件。
