# 阶段三：Python Agent 接入 TIA Portal V21

开发分支：`feat/tia-agent-integration`，最初基于 `bank32-v6`，2026-11-02 已 rebase 到队友最新提交 `ad3fa44`。

实现路径：题库快照 → 模型生成 Siemens SCL → 固定接口检查 → Python 调用 C# Bridge → 外部源导入/生成块 → TIA 编译 → 原始诊断反馈给模型 → 重编译。

本阶段提供独立的厂商编译流程。`compile_passed` 只表示 TIA 目标编译通过，`behavior_tested` 始终为 `false`；未进行 PLC 下载、仿真、扫描测试或 LTL 证明。原有 `task_backend` 的 `evaluate/replay` 需要实际运行轨迹，因此没有将编译结果注册为可执行行为后端，也没有把 SCL 送入原 ST 离线检查器。

## 1. 构建和配置

在仓库根目录运行，使用 Python 3.10+、.NET Framework 4.8 targeting pack 和已安装的 TIA Openness V21：

```powershell
# 非默认安装路径：本机使用此目录；按实际安装位置修改。
$env:TIA_OPENNESS_DIR = 'D:\download_2026\Simens\Automation\Portal V21\PublicAPI\V21\net48'
dotnet build integrations/tia_bridge/TiaBridge.csproj -c Release

python -m plc_agent.tia_cli configure `
  --executable "$PWD\integrations\tia_bridge\bin\Release\net48\TiaBridge.exe" `
  --template-project 'D:\download_2026\TIAProjects\PLC_Agent_Test\PLC_Agent_Test.ap21'

python -m plc_agent.tia_cli doctor
python -m plc_agent.tia_cli probe
```

源码默认使用 Windows 的 `Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48`，没有写死本机 D 盘目录。非默认安装可像上面一样设置 `TIA_OPENNESS_DIR`，构建与运行都会读取它；构建时也可以用 `-p:OpennessDir=...` 覆盖引用路径，运行时仍需设置 `TIA_OPENNESS_DIR` 为相应目录。西门子 DLL 不复制进仓库。

2026-11-01 的原始实测在旧 checkout 中将 `agent_data/tia.json` 配为第二阶段验证过的原有 EXE：`D:\下载\tia_openness_v21_starter\tia_openness_v21_starter\tia_bridge\bin\Release\net48\TiaBridge.exe`。Python 适配器兼容该 Bridge 的编译 JSON，无需先切换到新构建文件。上面的 configure 命令会切换到仓库内的新 Bridge；若暂不需要，直接使用当前本机配置即可。原实测使用 `deepseek-v4.1-flash-1017` 和 `qwen3.8-flash`。新 checkout 的本机配置不会自动从旧目录迁移，请在“模型与环境”保存本机路径与凭据。

新构建的 Bridge 首次调用可能弹出“Openness 访问”。由使用者手动允许；等待超时、权限拒绝和工程打开失败均保留为基础设施错误，不能作为源码编译错误让模型反复修复。即使阶段二允许了另一路径的 EXE，新路径仍可能需要授权。

使用专用、关闭并保存的测试工程作为模板。Python 每次复制**整个工程目录**，包括 System 等附属文件，在副本上生成块、编译和保存。输出目录必须位于模板目录外。模板不得指向生产工程。每次编译保存完整副本，因此长期实验需要自行管理磁盘空间。取消/超时只终止本次 Bridge 的进程树，不清理用户原有 TIA 会话；如果厂商 IDE 创建了独立进程，仍可能需要手动关闭残留窗口。

## 2. Workbench 操作

双击 `start.cmd`，或运行：

```powershell
python -m plc_agent.web --port 18765 --open-browser
```

1. 在“模型与环境”输入 API Key 和模型准确 ID。提供了 `deepseek-v4.1-flash-1017`、`qwen3.8-flash` 两个候选，实际可用性由服务商返回结果决定。沿用项目现有 DMXAPI 端点与服务端凭据保存逻辑。
2. 进入配置页会自动读取本机 TIA 路径；可保存配置并执行“TIA 正/负对照编译”。对照任务异步执行，可在工作台查看、停止，也会进入实验记录。
3. 在“题库与规约”导入 JSON。当前题库集中在 `datasets/course32.json`，可以导入该文件或使用页面提供的模板，再选择 `PUBLIC_02` 等题目。
4. 在代码工作台选择 `TIA Portal / Siemens SCL`，点击“生成并自动修复”。可通过“单题推理模式”选择服务默认、关闭或开启思考；Qwen 本次成功演示使用关闭思考。已有源码时先编译，再按诊断修复；空白时先调用模型生成。
5. “TIA 编译”只编译当前 SCL，不调用模型。“下载 .scl”导出源文件。CODESYS 与 TIA 各自保留当前题目的编辑草稿；TIA 模式禁用本地 ST 检查。

题库现有 `target`/`executor` 的离线语义没有改变；平台和方言记录在本次 TIA 运行与结果中。32 题的冻结 JSON 已在 `.gitattributes` 中禁用换行转换，读取时仍严格校验原 manifest SHA256。

## 3. 命令行调用

无需模型即可实际编译任意 SCL：

```powershell
python -m plc_agent.tia_cli compile examples/tia/MotorControl.scl
python -m plc_agent.tia_cli compile examples/tia/MotorControl_bad.scl
```

API 配好后从冻结题库生成，或从已有 SCL 开始修复：

```powershell
python -m plc_agent.tia_cli run PUBLIC_02 --model deepseek-v4.1-flash-1017
python -m plc_agent.tia_cli run PUBLIC_02 --model qwen3.8-flash
python -m plc_agent.tia_cli run PUBLIC_02 --source path/to/EdgeDetection.scl --max-revisions 5
```

也支持 `python -m plc_agent tia ...`；独立入口 `plc_agent.tia_cli` 只依赖 Python 标准库，适合只验证 TIA 的环境。`--home` 参数放在子命令前，可指向另一配置目录。导入题目的 `IMPORT_...` ID 也可用于 `run`。

## 4. 诊断与证据

`plc_agent/tia.py` 对 `TiaBridge.exe <project.ap21> <source.scl>` 使用参数列表、`shell=False` 调用，保存 stdout/stderr 文件，避免等待管道输出导致阻塞。仅接受唯一 `WB_RESULT_JSON=` 行，核对状态与退出码，成功还必须报告零编译错误。

- `compile_passed`：TIA 编译完成，零错误。
- `compile_failed`：TIA 编译报告错误，可交给模型修复。
- `generation_failed`：西门子在 `GenerateBlocksFromSource` 阶段抛出目标调用错误，可按原始诊断修复。
- `bridge_error`、`bridge_protocol_error`、`timeout`、`stale_evidence`：停止修复链，处理环境问题。
- `invalid_candidate`：缺少完整 FB 或改变固定接口，反馈给作者修复。

每次无种子任务最多生成 6 个版本（首次 + 最多 5 次修复）；有种子时为种子 + 最多 5 次修复。重复失败源码会提前停止。每轮检查取消和 1800 秒任务预算；单次模型请求和单次编译另有超时，因此总时间预算在阶段边界检查。模型请求失败直接记录，不做无界重试。题库的测试表不进入作者输入，只提供题面、接口、约束、LTL 规约和真实编译反馈。

当前网页运行使用统一目录 `outputs/single/<时间_题号>/`：最终源码为 `final.scl`，摘要为 `SUMMARY.md`，过程日志为 `run.log`，下列完整证据保存在其 `details/` 中。独立 TIA CLI 默认仍保存在 `agent_data/tia_runs`。2026-11-01 的旧网页运行使用 `agent_data/web_runs`，导出的验收报告保留该历史路径与原始哈希，不作改写。

- `task_snapshot.json`、`vendor_config.json`：任务与配置快照。
- `author_input_XX.json`、`author_XX.json`：作者输入及响应（不含 API Key）。
- `proposal_XX.scl`、`version_XX.scl`、`candidate.scl`：源码版本。
- `model_config.json`：模型公开配置与推理参数，不含 API Key。
- `compile_XX/request.json`、`stdout.txt`、`stderr.txt`、`result.json`、`project/`：每轮真实编译证据。
- `receipt.json`：最终状态、源码/数据集 SHA256、Bridge/适配器/模板主文件指纹、模型调用、Token 和耗时。

## 5. 验证状态

2026-11-01：仓库内 C# Bridge Release 构建通过（0 警告、0 错误）；TIA、Web API、导入题库共 23 项针对性测试通过。覆盖真实进程调用边界的模拟、工程副本及附属文件隔离、协议错误、固定接口、诊断回传、重复候选、基础设施错误停止、取消、超时及异步 Web 入口。

实际 Python → 第二阶段原有 Bridge → TIA 正例已编译通过（0 错误、0 警告，约 46 秒），负例返回 `compile_failed`（1 错误，`Tag #UndefinedOutput not defined.`，约 47 秒）。证据分别位于 `agent_data/tia_checks/legacy_positive_01`、`legacy_negative_01`，汇总为 `legacy_probe.json`。两次模板主文件哈希均保持不变，当前本机配置已选择该 Bridge。

首次 Python → 仓库内新 Bridge → TIA 调用触发 Openness 授权，等待超时返回 `EngineeringSecurityException`；证据位于 `agent_data/tia_checks/positive_01`。这不是编译通过证据。新 Bridge 需要在手动授权后重跑；真实模型生成和修复已使用第二阶段原有 Bridge 完成，见下方实测报告。测试中的模拟反馈不能作为厂商编译或模型效果证据。

旧离线数据集回归有一项需要当前环境未配置的 STruC++/g++，无法在本次 TIA 独立环境执行；未宣称全仓库回归通过。

```powershell
python -m unittest tests.test_tia tests.test_web tests.test_imported_bank -v
node --check plc_agent/web_static/app.js
```

## 6. 真实模型闭环验证已完成

同一冻结题目 PUBLIC_02：DeepSeek 首次 TIA 编译通过（0 错误、0 警告）；Qwen 关闭思考后，真实经历两次编译失败、两轮模型修复，最终以 0 错误、2 条警告通过。没有人工修改生成源码，也没有故障注入。

模型准确 ID 为 `deepseek-v4.1-flash-1017`；简称 `dsv4.1-flash-1017` 会被服务商拒绝。Qwen 默认设置曾有一次 180 秒服务端读取超时，已单独记录。这两组使用不同推理设置，作为流程展示，不作为公平能力比较。

完整源码、逐轮诊断、Token 与耗时见 [阶段三实测报告](../reports/tia_phase3_20261101/README.md)。

## 7. 第 8 项验收：三道不同题已覆盖

新增 PUBLIC_01（灌装线顺序控制）和 CUSTOM_01（电梯目标调度、数组接口），两题均由 DeepSeek 从空白自动生成 SCL，并首次通过真实 TIA 编译，均为 0 错误、0 警告。结合已有 PUBLIC_02，现已覆盖 3 道不同题、4 组端到端运行；PUBLIC_02 的 Qwen 记录提供两轮真实自动修复证据。没有人工编辑模型源码或注入故障。

第 8 项“选择 2～3 道 PLC 题，完成自动生成、编译与错误修复流程”已满足。该验收仍限于生成与厂商编译，不包含扫描行为或实机测试。新增两题的源码、日志、结果、调用用量和 SHA256 清单已补入 [完整验收报告](../reports/tia_phase3_20261101/README.md)。

## 8. Rebase 后的兼容性

保留队友的 A/B 模型配置、CODESYS + PLCverif/CBMC 检查、批量暂停/继续、历史记录与日志下载，以及新的启动与结果目录结构。TIA 使用独立的 SCL 编译流程，平台指标单独记录，不计为 CODESYS 编译通过或功能测试通过。

已修复自动合并引入的启动参数初始化丢失，并增加默认启动、web、codesys、tia 四种入口的回归检查。TIA 单题和编译器对照任务均能取消、保留日志并在历史记录中读取。旧数据集的部分验证测试缺少 fixture，形式化测试还需要 z3；这些本机限制不计作已通过。

2026-11-02 合并后检查：TIA、网页、历史记录、推理设置、批量实验及导入相关 64 项测试通过；主入口、TIA 和网页命令帮助正常。新题库 32 项 SHA256 校验与历史验收包 64 份文件哈希校验通过。本轮未重新调用真实模型或厂商编译器。
