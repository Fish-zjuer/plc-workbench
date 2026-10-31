# 从 GitHub 复现当前项目

## 范围

仓库包含代码、课程资料、两份可导入题库、队友2026-10-30原始交付数据、逐题测试/LTL/溯源、R4编译器补丁、版本锁定依赖与启动脚本。无需原作者 D 盘目录或相邻 plc-workbench 文件夹。

不分发 API Key、个人 agent_data、收费软件安装包、许可证或本机缓存。新机器配置后可复现系统功能和相同输入；在线模型、服务排队和硬件存在变化，不能保证逐次生成完全相同或固定通过率。现有历史候选及部分历史报告已在 experiments 中；全部个人历史会话和调试报告不属于新环境的运行状态。

## 1. 下载正确分支

```powershell
git clone --branch bank32-v6 https://github.com/Fish-zjuer/plc-workbench.git
cd plc-workbench
```

源码 ZIP 下载也应选择 bank32-v6。只下载仓库默认分支可能不是当前版本。

## 2. 安装依赖

Windows x64，Python 3.10+（建议3.12）、Git、Node.js 22+、npm、g++（本机验证14.2.0）需可从终端运行。另安装授权可用的 CODESYS；本机验证版本为 V3.5 SP22 Patch 4 / 3.5.22.40。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-reproduction.ps1
```

脚本复用哈希锁定 Python 安装、构建固定源码与补丁的 R4、激活 R4、在当前项目 .runtime 安装 Codex CLI 0.80.0，不发起模型调用。它需要联网。g++ 的 bin 目录应包含其运行时 DLL；仅 g++ --version 成功不保证其 cc1plus/as/ld 可用，最终须实际编译验证。

## 3. 校验并导入同一份数据

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/verify_reproduction_data.py
```

双击 launch-web.cmd → 题库与规约 → 选择文件 → datasets/importable/course32_20261030.json → 导入文件。网页从空列表开始，不会自动加载题库。该文件包含20公共＋12自建题；course32_baseline.json 是历史版本，勿同时导入后混合计分。原始队友资料在 datasets/team_delivery_20261030，早期冻结题库在 datasets/standalone32，SHA256和文件字节清单在 datasets/reproduction_manifest.json。

## 4. 配置 DMXAPI

网页“模型与环境”填自己的 Key 和准确模型 ID，Base URL 为 https://www.dmxapi.cn/v1。密钥只保存到本机。若要复现最近开发验证：两个模型分别 deepseek-v4.1-flash-1017、qwen3.8-flash，显式关闭思考；DeepSeek 参数 thinking.type=disabled，Qwen 参数 enable_thinking=false。模型档位按实际服务支持选择。

每轮最终生效的流式、输出上限、请求超时和额外参数应以实验 snapshot 中配置为准。开发验证使用 stream=true、max_output_tokens=32768、timeout=600、总并发4。网页已保存的默认配置不自动等同于这套开发参数；如需完全一致的开发配置，可在首次配置后、服务关闭时修改 agent_data/config.json 的相应公开字段，勿覆盖 private 下的密钥文件。

## 5. CODESYS 模板

优先在本机IDE保存专用空白 Standard Project：一个 Application、一个由任务调用的可编辑 PLC_PRG，包含对应设备和 Standard 库。不要直接拿含旧设备/旧库的安装模板运行。

对与本机相同的 SP22 Patch4 安装，可用随仓库的脚本创建副本（实际路径改成接收方自己的路径；目标不能已存在）：

```powershell
$env:WB_TEMPLATE_SOURCE = 'C:\YourCODESYS\Templates\Standard.project'
$env:WB_TEMPLATE_TARGET = Join-Path (Get-Location) 'agent_data\Blank_SP22.project'
New-Item -ItemType Directory -Path agent_data -Force | Out-Null
& 'C:\YourCODESYS\Common\CODESYS.exe' --noUI '--profile=CODESYS V3.5 SP22 Patch 4' ('--runscript=' + (Join-Path (Get-Location) 'scripts\codesys_prepare_template.py'))
```

脚本针对3.5.22.40设备及IoStandard 3.5.22.0，不保证其他版本通用。它只操作工程副本，不连接实体PLC。网页填写本机 exe、准确 Profile、新模板路径、120～300秒编译时限，保存并执行正/负编译对照；必须接受正确代码且拒绝错误代码。不能凭模板生成成功直接宣称编译环境通过。

## 6. 实验及边界

网页“实验记录”选择两个模型、各自推理模式、题库范围与并发，运行前检查通过后再开始2×2；这会收费。固定题库、版本、预算，四组都覆盖相同题目。程序与题库版本变化后需新轮次，不替换旧失败成绩。

PUBLIC_18在当前厂商模板存在VARIANT/PV兼容限制；本地通过不等于CODESYS通过。LTL文件存在不等于形式化证明。模型失败可能仍收费，未收到usage只能报告未知，不能编造。

## 验收

- 数据校验脚本通过；网页空列表可导入32题且显示测试/规约。
- R4 已校验激活，实际本地ST编译/执行成功。
- CODESYS正负对照通过，当前项目内Codex 0.80.0预检通过。
- 单题生成、编辑、测试、编译、导出可用；四配置可启动并分别保存记录。
- 新机器生成的 agent_data 保留于新机器，不与仓库样例成绩混用。
