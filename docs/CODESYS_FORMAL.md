# CODESYS 与形式化验证（R7）

R7 在通用任务闭环中加入 Z3，并实现官方 CODESYS CLI/脚本适配。2026-10-28 本机已实际运行 Z3；CODESYS 未安装，厂商编译与仿真尚未实测。适配器的协议测试和脚本替身测试不代表厂商验证通过。

## 两种工具分别解决什么

把 PLC 功能块理解成“带有持久变量、每次扫描调用一次的 C 函数”。测试挑一些输入序列实际执行；形式化工具把受支持的 ST 原文翻译成状态转移约束，搜索违反规则的输入，并尝试归纳证明规则在任意后续扫描仍成立。

CODESYS 检查另一件事：这份程序能否在指定的厂商编译器、设备模板和库中编译，实际仿真输出是什么。形式化模型正确不等于厂商兼容；厂商编译成功也不等于需求正确。两个结果分别保存。

完整流程：确认需求和不变量 → 弱模型生成 ST → 实际编译和场景检查 → Z3 搜索/归纳 → 隔离审查 → 反例重放 → 修订 → 导出。

## 形式化策略

在任务 contract.json 中设置：

```json
"formal": {"mode": "required", "bound": 20, "timeout_seconds": 20}
```

- off：保持旧任务行为，不运行求解器。
- best_effort：尝试证明，完整展示未支持或未完成的原因；有限检查通过仍不代表证明通过。
- required：所有已列不变量必须获得归纳证明，才能进入最终通过流程。语法未支持、超时、只有有界检查结果都会停止。

bound 是从声明初始状态寻找反例的扫描上界。没有在 20 扫描内发现反例，只能称 bounded_only。程序还会尝试 1..8 阶归纳；只有基例检查和归纳步骤均为 UNSAT，才把对应性质标为 proved。归纳步骤的 SAT 来自任意状态，不能直接称真实可达缺陷。

求解器直接读取实际 ST，模型不能另写一个更容易通过的验证模型。SAT 输入需要在同版本编译产物上执行两遍，逐行输出与符号输出一致，并确实违反同一已确认性质，才能自动加入回归集并交给作者修复。语义不一致时停止。

当前证明子集是一个完整 FUNCTION_BLOCK：BOOL、8/16/32 位整数与位串、局部/输出持久状态、声明初值、赋值、IF/ELSIF/ELSE、受限布尔/比较/加减。按声明宽度建模赋值后的整数回绕；拒绝混合类型隐式提升和比较中的变量算术中间值。支持 previous.inputs 和 previous.outputs；首扫描无历史时不触发历史性质。

计时器、REAL/LREAL、TIME/LTIME、外部函数/功能块、数组、指针、VAR_IN_OUT、循环、I/O 和中断不在此证明子集。未知语法不会被跳过。不对全部自然语言需求、实体设备、并发、热启动保留状态或硬件故障作证明。

使用入口：任务面板“形式化检查”；聊天工具 plc_task_formal；TUI `/task verify 任务ID`；终端：

```powershell
python -m plc_agent task verify 任务ID --project 项目ID --mode execute
```

报告保存源码、约定和求解器/前端指纹；每次查询保存为 SMT-LIB2 文件和校验值。改代码、改约定、改求解实现或删改查询文件，旧证明会显示 stale_evidence。SMT 查询可独立使用 `formal_verify.replay_query(path)` 重算；Windows 中文路径通过读取内容传入 Z3，避免底层 from_file 的路径限制。

## 配置 CODESYS

先从 [官方商店](https://store.codesys.com/en/codesys.html) 安装 CODESYS Development System，含 Scripting 支持。官方商店需要账号登录时由用户完成。

在 IDE 新建一个专用 Standard Project，保留一个 Application 和已被循环任务调用的空 PLC_PRG，切换 Simulation 后保存为 .project。不要选生产工程；适配器每次复制此模板，在副本中导入候选和测试驱动。模板内不能已有待测 FB。

```powershell
python -m plc_agent codesys doctor
python -m plc_agent codesys configure --executable "实际安装目录\CODESYS.exe" --profile "实际安装的完整 Profile 名称" --template-project "专用模板.project"
python -m plc_agent codesys probe
```

安装路径和 profile 不猜测；有独立实例时可加 --additional-folder。配置保存在本机 PLC_AGENT_HOME/codesys.json，模型没有修改配置或指定任意可执行程序的工具。

单独编译已确认任务：任务面板“CODESYS编译”，或 `/task compile 任务ID`。终端可执行 `python -m plc_agent task compile 任务ID --project 项目ID --mode execute`。结果 compiled_unit 只表示编译；不会把行为任务改成通过。

完整目标测试需在新任务中选择 `"target":"codesys", "executor":"codesys"`。后端调用官方 --profile / --noUI / --runscript，在工程副本中 rebuild、generate_code，保存非空 compiled.app 和哈希；仿真完成后读取真实输出，再交给固定判据判断。缺安装、库、配置或仿真失败会阻塞，不回退成本地结果。

当前仿真驱动只接受上述无时钟、无外部调用的 BOOL/整数子集。每个场景独立 FB 实例，在 PLC_PRG 一次执行中依序调用；time_ms 仅保留为轨迹编号对应时间，不能模拟 TON 等计时器。其他 ST 可尝试单独编译，不能借此声称完成行为验证。

脚本必须开启并读回 Simulation，才能 login；不配置实体 PLC 地址、不删除其他应用。共享 profile 有进程锁，支持取消及超时清理。API 调用依据 [官方 CLI](https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_commandline.html)、[应用编译接口](https://content.helpme-codesys.com/en/ScriptingEngine/ScriptApplication.html)、[仿真开关](https://content.helpme-codesys.com/en/ScriptingEngine/ScriptDeviceObject.html)、[在线读取接口](https://content.helpme-codesys.com/en/ScriptingEngine/ScriptOnline.html)。具体版本的监视、模板与仿真行为仍需安装后验证。

## 和外部 R5 合并

通用编排只调用 capabilities / evaluate / replay / fingerprint。R5 可以扩展或替换 codesys.py 中的目标适配器，保留固定约定、版本、反例、TUI 和证明层。需要重点核对时间推进、重置、库版本和 VAR_IN_OUT 别名；第 18 题的 VARIANT/PV_* 仍不能视为原生 CODESYS 接口。

实测记录见 [R7 报告](../experiments/formal_r7/report.md)。求解器来自 [Z3 官方项目](https://github.com/Z3Prover/z3)，安装依赖固定版本与 SHA256。

当前附带的依赖包和锁定文件面向 Windows x64；其他平台需选择对应 Z3 wheel 并重新验证。
