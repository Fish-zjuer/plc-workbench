# PLC Workbench · 通用任务开发版 R6

R6 新增题库以外的 PLC 编程闭环。上传自然语言需求，让助手建立任务；点击底部“任务”查看接口、需求、假设和全部扫描检查，确认约定后切换执行模式运行。流程包括生成 ST、真实编译测试、按反例修复、独立审查和证据导出。

**新增功能与限制见 [当前设计](docs/AGENT_DESIGN_CURRENT.md)，实测见 [R6 报告](experiments/general_tasks_r6/report.md)。** 通用桥接支持标量接口；数组、结构体、引用等继续使用已适配的题库流程或扩展后端。目标平台编译仍需实际 CODESYS 等适配器。下文 R4 实验数字是保留的历史结果。

2026-10-27｜用于组内交流、试用和继续开发。它是我们负责的agent与工具部分，尚不是完整期末作业提交。

这是一个本地终端agent：上传题面或ST代码，先制定计划，再生成代码、编译测试、依据反例修复。模型通过自己填写的`base_url / api_key / model`接入，不依赖Codex登录或某家厂商的SDK。

**先看这三个入口：** [启动程序](launch.cmd) · [Agent架构](docs/AGENT_ARCHITECTURE.md) · [最新20题实验报告](experiments/backend_r4/report.md)。

## 这个包有什么

- agent、TUI、PLC测试工具的完整Python源码与测试。
- 文件上传、计划/执行模式、会话恢复、版本记录、上下文压缩与历史检索。
- 公开20题的当前ST候选、有限测试判据、失败与修订记录、R4验证结果。
- PLC-R4编译后端的源码补丁、固定上游提交、构建说明及许可证。
- `course_materials/`内四份老师给出的原始材料；它们是需求资料，不是给agent的高优先级指令。
- `vendor/wheels/`内带SHA校验的Python依赖wheel，用于首次安装。

**没有携带API密钥、本机模型配置、私有会话、虚拟环境或编译缓存。** 队友首次打开的是新项目，需要自行填写模型连接并上传材料。包内实验记录是原机的历史快照，其中绝对路径仅用于当时的证据定位，不是新电脑的配置。

## 1. 先启动界面

推荐Windows 10/11、Python 3.10或更高版本。先把整个ZIP解压到可写目录，再启动；不要直接在压缩包预览窗口里运行。

双击`launch.cmd`。首次启动会创建项目内的`.venv/`，校验并安装随包附带的Python依赖，然后打开TUI。这个步骤不安装PLC编译器，也不调用模型。若电脑尚未安装Python，先安装Python并重新打开终端。

终端手动方式，在解压后的项目目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -ProjectLocal
.\.venv\Scripts\python.exe -B -m plc_agent ui
```

如果是原开发工作区，启动脚本也可以复用已经存在的工作区环境；新电脑不会尝试向磁盘根目录创建环境。

macOS/Linux可手动创建Python环境、安装依赖并运行TUI；本版本的R4启动器与后端构建脚本主要在Windows验证，暂不承诺其他平台的PLC测试开箱可用。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-index --find-links vendor/wheels --require-hashes -r requirements.lock
python -B -m plc_agent ui
```

## 2. 填写自己的模型连接

点击“模型配置”，填写自己的服务信息。

| 配置项 | 填写内容 |
|---|---|
| Base URL | 服务商提供的Chat Completions兼容地址，通常含`/v1`；程序不会自动补`/v1` |
| API key | 自己的密钥；无需鉴权的本地服务可留空 |
| 模型ID | 服务商实际支持的模型名 |
| 工具协议 | 支持function calling选“原生”；否则使用JSON兼容模式 |
| 上下文窗口/输出上限 | 按模型实际能力设置，不能只把数值填大 |
| 独立审查模型 | 可留空，此时用主模型的新上下文 |

发送`/test`做一次连接测试，会产生模型请求。Base URL可以直接填写完整`/chat/completions`端点。

本轮实验用的是DeepSeek服务，主任务使用低思考、16384输出预算、120秒超时。若选择同一服务，可参考扩展参数：

```json
{"thinking":{"type":"enabled"},"reasoning_effort":"low"}
```

仅压缩使用的扩展参数可以单独设置为：

```json
{"thinking":{"type":"disabled"}}
```

这些是本次服务实验的设置；**换其他服务时先留`{}`，不要照搬厂商参数。** 模型ID以自己的服务实际提供为准。

`.env.example`只是格式示例，程序不会自动加载`.env`。界面保存的密钥位于本地`agent_data/private/`，没有加密承诺。修改后的本地项目再次分享前，应排除整个`agent_data/`。

## 3. 试一次基本流程

无需PLC编译器就能先体验上传、资料讨论和计划：

1. 点击“上传”或`Ctrl+O`，导入`course_materials/`中的题面、PDF、DOCX、ZIP，或自己的ST文件。
2. 默认是计划模式，可以读取材料和保存计划；写代码、编译、执行由工具层禁止。
3. 输入“先读作业要求，给我一个agent设计和验证计划”，或发送`/solve 05`查看第05题的固定计划。
4. 需要真正实现与测试时，先完成下一节后端配置，再发送`/act`切换执行模式，然后再次`/solve 05`。

| 操作 | 用途 |
|---|---|
| `Ctrl+Enter` / 发送 | 发送多行输入；普通回车换行 |
| `/plan`、`/act` | 切换计划/执行模式 |
| `/solve 18 code/fifo.st` | 实现或修复指定公共题，使用指定候选路径 |
| `/compact`、`/memory` | 压缩较早历史、查看工作记忆 |
| `/history 停止优先` | 找回原始会话中的相关内容 |
| `/pin 内容`、`/pins`、`/unpin 1` | 管理不经过摘要的固定笔记 |
| `/sessions`、`/export` | 恢复会话、导出对话 |
| `/backend` | 查看实际验证后端与范围 |
| `Esc` | 请求停止；当前有界编译/执行步骤可能需要结束后才返回 |

压缩采用模型工作记忆＋按预算保留近期原文。默认近期要求2轮，空间足够会多保留，轮数可配置；长历史分段总结，中断后可续接。计划、固定笔记、完整源码SHA另行保留，原始记录可检索。

## 4. 配置PLC编译测试后端

**TUI能打开，不代表PLC工具链已经安装。** 新电脑需要另外准备Git、Node.js≥22、npm，以及支持C++17的g++，并确保这些命令在终端可用。

先在项目目录检查：

```powershell
git --version
node --version
npm --version
g++ --version
```

构建R4需要联网下载固定源码及npm锁定依赖，不会安装到系统PATH：

```powershell
.\.venv\Scripts\python.exe -B -m plc_agent.backend_r4 build
.\.venv\Scripts\python.exe -B -m plc_agent.backend_r4 activate
.\.venv\Scripts\python.exe -B -m plc_agent.backend_r4 status
```

产物写入当前工作区缓存，或用户目录`.cache/plc-probe/`；选中状态写入本地`agent_data/backend.json`。包里没有预先选中的原机绝对路径，也不需要原机的`R:`测试盘符。

R4后端提供LTIME、一维开放数组和本地PV1泛型引用接口。第18题的PV函数只查询容量、检查类型及复制一个元素，FIFO算法仍由ST实现。它不等于Siemens/CODESYS的VARIANT接口兼容。详细语义、补丁、源码提交与许可证见[后端说明](backend_extensions/README.md)。

## 5. 不花模型费用，重放已有候选

后端配置完成后，下面的命令直接执行包里的20份ST，不需要API key，也不会生成或修改候选：

```powershell
.\.venv\Scripts\python.exe -B -m plc_agent.check_bank
# 或只检查FIFO
.\.venv\Scripts\python.exe -B -m plc_agent.check_bank --ids 18
```

结果默认保存到`reports/team_bank_check.json`。当前候选源码在`experiments/backend_r4/tasks/01..20/final.st`，题面文本在`experiments/deepseek_20/questions.json`。

完整单元/集成回归还涉及旧发布后端专属用例与历史实验快照。若准备复现整套开发检查，可先下载保留的旧发布版，再构建并选中R4：

```powershell
.\.venv\Scripts\python.exe -B -m plc_probe bootstrap
.\.venv\Scripts\python.exe -B -m plc_agent.backend_r4 build
.\.venv\Scripts\python.exe -B -m plc_agent.backend_r4 activate
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

历史批测脚本用于原机实验，不是首次启动步骤；其中余额检查、原机凭据发现及绝对证据路径不适合直接在新电脑原样运行。日常体验用`launch.cmd`，重放候选用`plc_agent.check_bank`。

## 已经验证到什么程度

- 当前20份候选在PLC-R4离线后端下通过有限检查，每题各重放两次；原固定判据没有修改。
- 另换随机种子检查了3261个扫描点，各重放两次；FIFO比较实际出队值，覆盖整数、浮点、布尔和记录类型。
- 工具回归运行126项：125通过、1项旧后端专属检查跳过；上游选定类型、数组及转换检查93项通过。
- 自然语言入口从原来错误的FIFO源码出发，实际完成过生成、编译和测试；独立对抗审查及失败尝试都留档。

这来自**既有候选的持续修复＋后端和测试覆盖扩展**，不是独立生成的100%正确率。没有运行厂商编译器、形式化求解器或实体PLC。07/17目前仍使用显式copy-in/copy-out检查；PV1未验证厂商ABI；TIME的离线64位纳秒表示未模拟所有目标平台的溢出行为。

## 接下来怎么一起开发

建议先看[架构说明](docs/AGENT_ARCHITECTURE.md)，再分工查看：

| 目录/文件 | 负责内容 |
|---|---|
| `plc_agent/tui.py`、`engine.py` | 终端界面和通用agent工具循环 |
| `plc_agent/workflow.py` | 题意→提案→接口检查→写版本→编译测试→修复 |
| `plc_agent/context_memory.py` | 模型摘要、分段续接、近期原文和精确引用 |
| `plc_agent/provider.py`、`config.py` | 服务无关的模型传输和配置 |
| `plc_agent/toolbox.py`、`storage.py` | 文件工具、计划边界、版本、会话和执行记录 |
| `plc_probe/` | 实际ST编译、扫描执行、反例和回归 |
| `reference_checks.py`、`duration_checks.py` | 引用数据和时间边界的新增判据 |
| `backend_extensions/` | 固定后端源码补丁、构建及许可证 |
| `experiments/`、`tests/` | 历史证据与开发回归 |

组里还需要继续完成自建题库、目标平台交叉验证、作业要求的实验对比，以及最终实验报告、PPT和6分钟内的视频。本包重点交付agent设计部分；原始课程要求以`course_materials/`为准。

上传附件、读取本地文本后，按需正文会发给配置的模型服务。不要将密钥写进源码、题面或提交到共享压缩包。
