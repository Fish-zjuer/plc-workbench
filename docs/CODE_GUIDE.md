# 当前代码导读

## 日常启动

只双击根目录 `start.cmd`，它会准备项目内 Python 环境并打开网页。等价命令是 `python -m plc_agent`。`python -m plc_agent web` 仅用于指定端口；`python -m plc_agent codesys` 用于配置和检查CODESYS；`python -m plc_agent tia` 提供TIA环境、检查和运行入口。这些是同一个程序的子命令，不需要逐个执行。

结果直接在 `outputs/` 文件夹中查看，或者从网页下载日志。已经删除只负责打开资源管理器的 `open_outputs.cmd`。

## 主流程

| 模块 | 职责 |
|---|---|
| `web.py`、`web_static/` | 网页入口和交互 |
| `campaign.py` | self/Codex 统一预算、模型调用、提交检查和批量对照 |
| `dataset_workflow.py` | 作者输入、返修和终止条件 |
| `codesys_dataset.py` | 编译、功能测试、形式化接口的统一检查链 |
| `codesys.py`、`codesys_worker.py`、`codesys_tests.py` | CODESYS 通信、IDE 内脚本和真实仿真测试 |
| `dataset.py`、`imported_bank.py`、`bank32.py` | 冻结题库、导入、测试判据与按实际后端选择的作者提示 |
| `provider.py`、`config.py`、`inference.py` | 模型连接、本机配置与推理参数 |
| `run_output.py`、`storage.py` | 输出、摘要、用量和文件保存 |
| `st_source.py`、`task_spec.py` 等 | ST 源码解析与共享数据约定，不是启动入口 |
| `dataset_formal.py` | 所有题目的统一LTL入口、编译/测试与形式化结论分离 |
| `ltl_adapter.py` | 统一读入公式、采样语义、观察器及模型包装 |
| `plcverif_backend.py`、`plcverif_st.py`、`cbmc_model.py` | 工具配置、有限语法适配、PLCverif建模、CBMC检查、有限LTL监视器、超时及证据保存 |
| `plcverif_references.py`、`reference_observers.py` | 调用方存储/共享引用、DINT下标适配、08逐通道帧条件、18独立队列、具体形状与值域证据 |

单题：网页 → dataset_workflow → Trial → evaluate_candidate。批量：Campaigns → self/Codex → 同一套 Trial 和 evaluate_candidate。

默认由 CODESYS 编译并仿真测试。只有显式取消 CODESYS 选项才调用本地备用方案。编译、功能测试和形式化状态分别记录；形式化自动调用PLCverif与CBMC，按性质记录界内通过、反例、超时和不支持。公式与辅助定义位于 `datasets/course32.json`，不存在只允许CUSTOM_09/10进入验证的题号分支。统一入口不代表全部题目特性已获准确建模，限制见FORMAL_MAIN_FLOW.md。

## 历史工具与本地备用目录

- `plc_agent/legacy/`：21 个旧终端、通用 agent、任务 CLI、旧批测与调试模块。网页不加载这套入口。需要研究旧实现时，显式运行 `python -m plc_agent.legacy --help`。原终端启动器集中在 `scripts/legacy/`。
- `optional_local_tests/`：本地编译与执行、结构体和数组驱动、专用作者提示、R4 安装工具及编译器补丁。没有 CODESYS 的同学保留它；仅提交 CODESYS 主流程时可以整体删除。
- `formal_verify.py`、`formal_st.py`、`task_formal.py` 等保留旧验证实验和共享解析/检查实现，不作为当前网页独立入口。本次目录整理不修改其验证能力。

`plc_agent` 顶层 Python 文件从 58 个减少到 32 个。剩余文件是分工模块，不是 32 个要执行的程序。没有把它们强行合成一个大文件，以便保留代码生成、实际测试、预算和结果记录的清晰职责。

## 提交与版本控制

`.gitignore` 排除本机密钥、安装环境、缓存、运行输出、旧实验报告、编辑器配置和 CODESYS 生成文件。`optional_local_tests/` 与 `plc_agent/legacy/` 是源码，明确保留在版本控制中，方便其他同学使用；不能靠忽略源码来代替拆分依赖。

`.gitignore` 不会自动取消已经跟踪的文件；精简的TIA验收报告是有意跟踪的公开证据。

回归源码在 `tests/fixtures/`；旧终端与备用流程的开发测试需要相应源码目录。删除备用目录后可照常启动 CODESYS 网页流程，但不能要求其本地专用测试继续运行。


## 2026-11-08 全集新增索引

- `tia.py`、`tia_cli.py`、`tia_workflow.py`：TIA配置、CLI和SCL生成/修复/检查，复用Trial/Campaign。
- `tia_scl.py`、`tia_formal.py`、`tia_tests.py`、`tia_runtime.py`、`behavior_plan.py`：SCL边界适配、共享验证入口、测试驱动与独立仿真运行器。
- `integrations/tia_bridge/`：Openness工程操作与PLCSIM运行器C#源码/项目；`integrations/tia_trial_ack/`：可选通知辅助源码。
- `adversarial_review.py`：独立ST审查与建议轨迹重放；审查意见保持人工待复核。
- `reports/tia_final_20261104/`：队友原始TIA代表性验收证据；`docs/validation/`：历史本地重放与审查证据。
- `docs/TEAM_INTEGRATION_20261108.md` / `.json`：统一进度、11分支/5PR台账、历史结果范围和本次整理边界。

旧的模块数量与迁移说明属于整理当时的记录。日常入口仍是start.cmd，无需逐个运行上述模块；本全集没有把历史验收改记为合并后的新实测。
