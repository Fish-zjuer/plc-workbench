# CODESYS 与网页 2×2 实验

## 先配置环境

1. 使用本机实际安装的 CODESYS，保存一个专用的空白 Standard Project 模板，包含一个 Application 和已配置任务的 PLC_PRG。只使用该模板的副本，过程不会下载到实体 PLC。
2. 网页“模型与环境”填写准确 CODESYS.exe、Profile 名称、模板 .project 路径及超时，保存配置。
3. 点击“验证编译器（正/负对照）”：同一路径必须接受正确 ST、拒绝含未定义变量的错误 ST，才算环境检查通过。没有安装/配置时会明确报错。
4. 工作台可以对编辑器当前源码点击“CODESYS 编译”；它与“本地检查”独立。真实厂商编译会保存应用映像、源哈希、IDE版本、诊断、执行指纹和证据目录。结构体、辅助函数与主功能块按原源码拆成多个 CODESYS 单元导入，不改写可执行语句。
5. 配置 DMXAPI Key 和准确模型 ID。批量实验还需要本地 ST 编译器和 g++；其环境沿用现有 `PLC_AGENT_HOME`、`STRUC_PP_HOME`、`CXX` 与 PATH。

本机已发现 CODESYS V3.5 SP22 Patch 4（3.5.22.40）。安装目录附带的 Standard.project 使用旧版设备和库，不能直接作为此环境的编译模板；本机专用副本为 `agent_data/codesys_template/Blank_SP22.project`，更新设备及 IoStandard 引用后已通过真实正/负对照：正确代码编译并生成应用映像，含未定义变量的代码被编译器拒绝。这是环境验证，不代表题库测试通过。

## 在网页启动四设置

打开“实验记录”页：

1. 输入 DMXAPI 模型 A 和模型 B 的准确 ID，两者必须不同。
2. 先在题库页选择电脑上的文件导入题目，在工作台选中该导入版本的题目，再将题库范围设为“当前所选题库版本全部题目”。正式实验应覆盖所选版本全部公共和自建题。“当前题目”只用于小规模调试。
3. 保持勾选“实际调用 CODESYS 编译”。取消勾选只产生本地试跑结果，不是作业要求的厂商编译结果。
4. 点“运行前检查”，解决显示的配置问题；再点“开始 2×2 实验”。该按钮会开始收费调用；N 道题对应 4N 个任务，大批量可能耗时数小时，不会自动替换模型或无限重试。
5. 交错调度 self-A、self-B、Codex-A、Codex-B，任务并发数可设为 任意正整数（默认 16，实际并发不超过本批次任务总数）；同一 CODESYS Profile 的编译排队执行，模型请求及不同任务的本地测试可并发；页面每2秒显示进度。可停止，并从历史下拉框查看或导出 JSON。

四设置共享：原题快照、LTL/附加约束、后端说明、检查器、6个不同源码版本上限、24次模型请求上限和1800秒单题上限。基础设施故障也计入请求预算，批量任务不重新获得预算。服务重启后未完成批次显示 interrupted，不冒充完成。

输出：`agent_data/campaigns/<ID>/campaign.json` 与 `tasks.json`；每组/模型/题目的目录含 task_snapshot、候选、各版本编译/测试证据和 receipt。快照保存代码哈希和无密钥模型配置，运行中改变代码会终止下一任务。网页在运行中禁止修改模型与CODESYS配置。

汇总分别记录首次/最终 CODESYS 编译通过数、首次/最终本地任务通过数、场景测试计数、逐次 usage 与 Token 汇总、耗时。缺少 usage 显示不完整，不把失败调用当零成本。LTL仍是需求层规约，未接入模型检查器时不宣称证明通过。CODESYS成功并不保证本地后端成功（例如专有扩展差异），两者分别记录。

## Codex 基线接入约定

当前 Chat Completions 中转适配固定项目既有 **Codex CLI 0.80.0**。优先寻找项目或相邻 `plc-workbench/.runtime/codex-0.80/node_modules/.bin/codex.cmd`，也可通过 `PLC_CODEX_CLI` 指定同版本路径。新版CLI不直接套用该配置，预检会报告不兼容；官方当前配置参考只列 Responses 接口：https://learn.chatgpt.com/docs/config-file/config-reference 。

基线使用真实CLI，不把自研循环改名为Codex。CLI采用临时CODEX_HOME、工作目录、Chat协议计量代理和短期本地token；DMXAPI真实Key不进入CLI环境。模型响应工具调用和检查器通过本地HTTP往返；测试表留在主机，CLI只收到与self一致的作者输入包和修复诊断。CLI的工作目录限制仍依赖所用Windows sandbox和指令遵从，不能声称强隔离读取是已证明的。

本次完成CLI真实工具往返的本地模拟服务测试，没有使用真实DMXAPI Key；具体模型是否支持CLI所需工具调用，仍需小规模实际试跑。

## 自动化脚本

在项目根目录和同一个配置环境运行。默认仅检查，添加 `--execute` 才发起模型实验：

```powershell
python -m experiments.bank32.run_four_way_web --model-a '准确模型A' --model-b '准确模型B'
python -m experiments.bank32.run_four_way_web --model-a '准确模型A' --model-b '准确模型B' --execute
```

小规模本地试跑：

```powershell
python -m experiments.bank32.run_four_way_web --model-a '准确模型A' --model-b '准确模型B' --ids PUBLIC_01 --local-only --execute
```

也可以不生成代码，只批量检测已有 ST。准备 manifest.json，路径相对manifest所在目录：

```json
[{"task_id":"PUBLIC_01","source":"candidates/PUBLIC_01.st"},
 {"task_id":"CUSTOM_01","source":"candidates/CUSTOM_01.st"}]
```

```powershell
python -m experiments.bank32.check_candidates --manifest manifest.json --output reports/new_vendor_checks
```

`--local-only`跳过厂商编译，`--home`指定保存模型/CODESYS/导入题库配置的目录。不覆盖已有输出文件夹，不发起模型调用。实际测量必须基于当前题库版本重新执行，不能继承旧版本的实验结果。
