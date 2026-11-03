# TIA 原生仿真环境与验收（2026-11-03）

当前已完成环境配置，CUSTOM_09 的既有模型生成代码连续两次通过完整检查；模型修复版也已在独立运行器上完成真实原生测试和共享有界形式化。验收摘要保存在 `reports/tia_native_20261103/`，先前的超时失败全部保留。

此前一次独立运行器集成复验在 TIA 会话初始化阶段返回 `EngineeringSecurityException`，约 221 秒后结束；未开始编译、未创建仿真实例，与 PLCSIM PowerOn Timeout 分开记录。使用者随后从自己的终端运行 `.tmp-tests/tia-stable-rerun-20261103/recheck_from_terminal.ps1`，同一版本 Bridge 与模型修复代码完成全流程：TIA 编译 0 错误、0 警告，上电 9.188 秒，25 场景 / 48 采样 / 192 断言全通过，10/10 共享形式化在 20 扫描上界内通过。新增模型请求为 0，仿真实例已关机并注销；日志确认运行器没有加载 Openness。该单次结果不能证明所有冷启动已稳定，也不能由此确定此前超时的唯一原因。

此后 Agent 再次启动两个完整 Trial，同一源码上电分别为 8.128 秒、12.128 秒，两轮候选编译均为 0 错误、0 警告，行为与形式化仍全部通过，实例均已清理。独立运行器累计三轮完整通过，原始记录为 `manual-runtime-host-20261103-195607`、`model-repair-runtime-repeat-1`、`model-repair-runtime-repeat-2`。使用者明确反馈手动终端那轮只确认了 PLCSIM 试用提示，没有重新允许 Openness；后两轮的窗口交互未单独记录，因此不称为无人值守验证。重复验证均新建仿真实例，不涵盖操作系统重启或全部负载条件。

## 本机环境与模板

- TIA Portal V21 / Openness net48，PLCSIM Advanced V8 x64 API：`C:/Program Files (x86)/Common Files/Siemens/PLCSIMADV/API/8.0/Siemens.Simatic.Simulation.Runtime.Api.x64.dll`。已验证 Siemens AG 签名有效、64 位 API 可加载、运行时可访问。公共目录自动发现已补齐。
- 编译模板继续使用原 S7-1200 工程。仿真使用 CPU 1511-1 PN（`6ES7 511-1AK02-0AB0`）/ V2.9：`D:/download_2026/TIAProjects/WB_S7_1500_Card_FW29_20261103/WB_S7_1500_Card_FW29_20261103.ap21`。项目仿真支持已开启；创建时硬件和软件编译为 0 错误、1 条显示屏未设置密码警告。路径保存在忽略的 `agent_data/tia.json`。
- 专用离线模板保留 CPU 访问密码，配置数据加密明确设为 None。此前的加密 v3 模板保留，未修改实体 PLC，也没有网络下载。密码文件只保存在忽略的本机状态目录。
- 受保护模板的虚拟卡曾成功导出，但 PowerOn 返回 `WarningPasswordForProtectionError`。文件夹导出未完成 PLCSIM 所需的、与 Windows 用户绑定的配置密码下装。该限制仍保留，不把受保护工程描述为已支持。

## 上电与会话改动

1. 自动调用默认使用 `WithoutUserInterface`，通过 Dispose 关闭自身创建的 TIA 会话。此前图形会话残留导致可用内存下降至约 1 GB。需要交互演示时可选 `TIA_BRIDGE_WITH_UI=1`，其界面需自行关闭。
2. 使用模板的实际 CPU 订货号注册实例，使用 API 要求的 19 字符格式（含空格），替代 `CPU1500_Unspecified`。
3. PowerOn 的固件等待参数从 60 秒改为 180 秒；这不会延长试用许可提示的独立确认期限。上电前、成功后和失败时均保存运行状态、许可、具体 CPU 与耗时。总时间预算不足时，在创建实例前拒绝测试。
4. 已处于 Off 状态时不重复 PowerOff；清理已注销实例正常结束。避免用 `InvalidOperatingState` 或 `DoesNotExist` 掩盖原始失败。
5. 工程准备与仿真运行分为两个 EXE：Bridge 关闭 TIA 后，将导出的虚拟卡交给不引用 Openness 的 `TiaRuntime.exe`。源码、组合测试驱动、虚拟卡、Bridge 和运行器均绑定哈希。三个真实离线负例分别篡改源码身份、卡内容和运行器身份，均在加载仿真 API 前拒绝；Python 也会拒绝运行期间被替换的运行器所产生的证据。

西门子官方 Trial License 说明明确指出：启动时必须在规定时间内确认试用提示，否则实例不会启动，需要重新启动并确认。即使传入 180 秒固件等待参数，本机仍复现约 63 秒的初始化超时。试用实例会显示 21 天提示，需要使用者及时手动点击 OK；它与 Openness 访问授权不同。未使用 UI 自动化关闭最终重跑中的提示，未改变许可证设置。试用到期后需要有效许可。启动超时仍作为环境错误停止，不能伪装成候选代码失败交给模型反复修复。

诊断用的三个独立 API 上电实验中，两次分别在 19.274 秒、9.344 秒启动并完成既有模型代码的测试驱动，第三次超时；第三次的提示是否及时确认未能核实。此前另有两次诊断超时，原始记录全部保留。因此不能声称所有启动失败均已排除。

后续复测中，使用者明确反馈没有看到试用窗口，另一次无法找到命令行报告的窗口。因此不能仅凭 Timeout 判断是未点击 OK，也不能要求使用者寻找已经退出的 PID。修复版虚拟卡在独立 PowerShell API 宿主和不引用 Openness 的 C# 宿主中分别用 26.008 秒、63.196 秒上电并完成驱动；这些诊断没有采集判卷所需的完整输出，不能代替原生行为验收。同一 Bridge EXE 内不初始化 TIA 的子进程方案仍复现 62.328 秒超时，故进一步拆为独立 EXE，尚不能据此声称根因已排除。

## 模型代码完整重跑

题目为 CUSTOM_09：光谱仪维护后标定许可状态机，仅涉及 BOOL、USINT 与跨扫描状态，不含开放数组、VARIANT、浮点近似或候选定时器。

代码由先前的 `deepseek-v4.1-flash-1017` 请求生成。本轮按原 receipt 校验 SHA256 后重跑，未人工修改源码；两次重跑新增模型调用均为 0。

源码 SHA256：`0f8d72243d08fc9424d1243e7defb76503fc16961283b69b08df44364e5424de`。

| 重跑 | 上电秒数 | 场景 / 采样 / 断言 | 行为失败 | 共享形式化 |
| --- | ---: | --- | ---: | --- |
| model-rerun-1 | 9.368 | 25 / 48 / 192 | 0 | 10/10 bounded_pass，扫描上界 20 |
| model-rerun-2 | 9.128 | 25 / 48 / 192 | 0 | 10/10 bounded_pass，扫描上界 20 |

两轮均经过真实 TIA 编译、硬件编译、测试驱动编译、虚拟卡导出、PLCSIM PowerOn/Run/变量采样、共享判卷与共享形式化；关机和注销成功。PowerOn 与许可回执均为 `WarningTrialModeActive`，不是忽略许可证错误。候选代码 TIA 编译保留 4 条 State 相关未初始化警告。

原始证据：`.tmp-tests/tia-stable-rerun-20261103/`。使用同一题、同一源码重复运行只说明有限的重复性，不代表全部题目或所有系统负载下的稳定性。

## 自动修复与正负对照

已知负例由助手从题面编写的正例中构造：退出维护时直接跳到就绪态。此前真实行为测试在 192 项断言中检出 5 项失败，形式化按共用行为门禁不执行。

本轮从相同负例开始，执行“编译通过 → 真实行为失败 → 模型修复 → 重编译 → 原生复测 → 共享形式化”。真实负例复测再次检出 5 项失败后，模型用 1 次请求生成修复版（SHA256 `34b89c353ce7145fc470d67f034fc553d6304dadf71b5de9b362d3be5ddd3321`），TIA 编译为 0 错误、0 警告。修复版早期复验遇到 PowerOn Timeout 或 TIA 安全访问初始化超时，相应轮次未完成验收。使用者终端重跑 `manual-runtime-host-20261103-195607` 直接复用相同源码，未额外调用模型或人工修改代码，原生行为 192/192、共享形式化 10/10 bounded_pass。至此该单题修复结果完成验收；全流程包含手动发起的复验，不声称此前受环境中断的单次自动运行自行恢复。

先前独立的形式化预检查仅作为辅助证据：助手正例 10/10 有界通过；负例 P01、P03、P05 检出源模型反例，其余 7 条有界通过。模型修复版也完成独立的 10/10 有界预检查，上界 20，源码 SHA256 与模型回执一致。预检查没有越过完整 Trial 的行为门禁，不与完整任务通过率混算。

## 范围与限制

- 仅验证一个简单题。有限原生测试与 20 扫描上界内的形式化不等于无界证明，也不代表实体 PLC 验证。
- PUBLIC_08 的开放数组/VAR_IN_OUT 精确形式化由队友维护的共享模型处理；PUBLIC_18 的原生 VARIANT ABI 与共享模型仍不齐全，明确记为不支持。
- 未修改 `cbmc_model.py`、`plcverif_backend.py`、`plcverif_st.py`、`ltl_adapter.py` 的验证算法或模型。
- Bridge 与独立运行器构建 0 错误、0 警告；26 项 TIA 回归测试通过，另有 3 个真实运行器交接拒绝检查通过。2026-11-01 的 64 个原始交付文件 SHA256 均未改变。

参考：[试用提示与超时](https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced/installing/introduction/trial-license?contentId=xlNJOAPK2cqXCzika8BSFQ)、[实例注册 API](https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced-api/ibaseruntimemanager/simulation-runtime-instances?contentId=rpKc9xUCBPScBU4mFMNjMw)、[PowerOn 状态与超时](https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_dede_21/ubergreifende-informationen/funktionshandbucher-cpu/s7-plcsim-advanced-api/iinstance/betriebszustand?contentId=cLaviKYw6H1dyQNGbK2MIw)、[TIA 会话释放](https://docs.tia.siemens.cloud/r/en-us/v21/tia-portal-openness-api-for-automation-of-engineering-workflows/tia-portal-openness-api/general-functions/terminating-the-connection-to-the-tia-portal?contentId=WXR9ZOT2OwdSOTPD82o5dg)、[配置数据密码](https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced/product-overview/password-to-protect-confidential-configuration-data?contentId=J0Hr5zxhFO0J3qNDS1fWAA)。
