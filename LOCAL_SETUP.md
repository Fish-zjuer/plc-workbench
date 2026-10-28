# 本机搭建与实验入口

本地仓库位于 `D:\大三上\GenAI赋能工业编程\final project\plc-workbench`，分支为 `codex/assignment-experiments`，基于上游提交 `42bdf36`。当前阶段准备本机 Agent 与编译测试环境；模型服务尚未配置，未发起收费模型请求。

## 已验证的环境

- 项目内 `.venv`：Python 3.14，Textual 8.2.8，pypdf 6.21.2；依赖从本机 R4 分享包导入并按仓库 SHA256 校验安装。
- Node 24.22.1，私有 npm/npx 10.9.2，MinGW g++ 14.2.0。
- 已构建、校验并激活 PLC-R4：固定 STruC++ 提交及仓库补丁。
- 20份已有 R4 候选在本机通过一次离线有限检查，结果见 `reports/local_public20_check.json`。这是重放已有候选，不是新的模型生成实验。
- CODESYS 3.5 SP22 Patch 4：实际生成测试功能块的目标代码，且确认故意写错的程序被拒绝。结果见 `reports/local_setup/codesys/receipt.json`。
- 完整工具回归129项：128项通过、1项旧后端专属检查跳过。已补齐上游缺少的 MCP 启动文件 `agent_tools.py`；日志见 `reports/local_regression.log`，汇总见 `reports/local_setup/status.json`。

MinGW 放在用户目录的英文缓存路径，避开中文安装路径下链接器无法定位标准库的问题。`.runtime/toolchain.json` 保存本机工具路径，启动脚本只为子进程设置环境，不修改系统 PATH。

CODESYS 自带 Standard.project 使用旧 PLCWinNT 设备。检查器只复制并升级测试工程到本机安装的 Control Win V3 x64 3.5.22.40，不改动自带模板，不连接或下载到 PLC。

现已给20道公共题的现有 R4 候选逐题测量真实 CODESYS 编译：18/20通过，90%；第18题与第20题失败。完整结果见 [逐题报告](reports/codesys_public20/20261027_r4_baseline_02/report.md)；失败原因分析见 [诊断说明](reports/codesys_public20/20261027_r4_baseline_02/analysis.md)。全部候选已按原始字节冻结，本轮没有修复源码，也没有调用模型。

## 常用命令

在仓库目录打开 PowerShell：

```powershell
# 启动终端界面，也可直接双击 launch.cmd
.\launch.cmd

# 查看模型配置是否就绪，不发请求
.\scripts\run.ps1 -m plc_agent doctor

# 查看已激活的 R4 后端
.\scripts\run.ps1 -m plc_agent.backend_r4 status

# 无 API key 重放已有20份候选
.\scripts\run.ps1 -m plc_agent.check_bank --output reports/local_public20_check.json

# 重验真实 CODESYS 编译器，含一个故意出错的对照
.\scripts\run.ps1 -m plc_agent.codesys_check --executable 'D:\大三上\GenAI赋能工业编程\codesys\CODESYS\Common\CODESYS.exe'

# 逐题测量现有公共20题的 CODESYS 编译结果，默认建立新的带时间目录
.\scripts\run.ps1 -m plc_agent.codesys_bank --executable 'D:\大三上\GenAI赋能工业编程\codesys\CODESYS\Common\CODESYS.exe'

# 运行工具回归
.\scripts\run.ps1 -m unittest discover -s tests -v
```

如需在当前终端直接使用 `python`、`g++` 和 `npm`，先执行 `. .\scripts\activate.ps1`。

## 下一阶段实验

用户负责 Agent 与实验；队友负责不少于10道自建题及逐题 LTL。真实模型配置完成后，需要冻结公共题与自建题、测试与资源预算，按“现有框架/自研框架 × 模型A/模型B”运行四组独立实验。

正式结果必须分别记录首次及修复后的 CODESYS 编译结果、功能测试、请求/Token用量、耗时与失败原因。离线重放结果不能替代作业要求的 CODESYS 指标。当前模型配置为空，因此不能开始新的真实模型生成，也不能把仓库历史修复记录计入这四组实验。

原始作业资料保留在仓库上一级目录；已核对本地公共20题的题面与仓库题库逐题完全一致。

## 已启用的 Agent 流程优化

本机现在启用 `codesys` 验证模式，`/solve` 和 `plc_bank_test` 要求“静态检查 → CODESYS编译 → 有限离线行为测试”均通过。新增保留字检查、平台接口预检、重复失败候选停止、按版本失效的编译缓存及严格验证记录。模型连接仍为空，优化后的真实生成能力尚待API实验。

详见 [R5优化说明](docs/AGENT_OPTIMIZATION_R5.md)。原来的90%基线保留；测试副本的修复不写回公共候选目录。
