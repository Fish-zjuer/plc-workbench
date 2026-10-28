# 公共20题四组测试操作说明

只评价课程已有20题。四个条件为Codex CLI0.80.0/自研PLC Agent分别使用deepseek-flash和qwen3.8-max。2026-10-28用户明确授权本轮新增不超过50元，独立campaign four_group_20261028；此前public20_20261027账本保留，不重置、不合并为新支出。

在项目PowerShell中先执行：

```powershell
. .\scripts\activate.ps1
$env:PLC_EXPERIMENT_THINKING='1'
$env:PLC_EXPERIMENT_QWEN_MAX_THINKING='0'
$env:PLC_EXPERIMENT_MAX_OUTPUT='32768'
$env:PLC_EXPERIMENT_UPSTREAM_TIMEOUT='600'
$env:PLC_EXPERIMENT_PROVIDER_TIMEOUT='620'
python -X utf8 -B -m experiments.public20.run --ids all --settings all --campaign four_group_20261028 --run-id full_v3 --budget-cny 50 --workers 2 --timeout 1800
```

同名批次已经启动时不要重复执行。runner默认拒绝覆盖；明确续跑用`--resume`，并要求相同代码、模型参数、测试指纹和预算。已完成结果不会因失败而自动重试或删除。中断且未形成结果的证据保留，相关题应以新的run-id记录重跑原因。full_v2/v3属于接入排障而中断的历史批次，不能混入正式矩阵。

模型请求通过本机计量中继转发到已有LiteLLM服务`http://127.0.0.1:4000`。中继与统一校验服务在本次runner中启动，默认端口8767；任务工作区只有本地临时凭据，没有提供方密钥。Codex和自研均使用同一检查器及原始反馈，再由各自框架组织上下文。Codex工作区在用户TEMP下`plc-baseline/`，目录独立不等于已经实施操作系统级读隔离。

每题共用限制：初稿+至多5次修复，最多6个不同源码提交；重复检查同一SHA不消耗版本。最多24个模型请求，单请求600秒、输出32768 tokens，任务总时限1800秒。2个任务并行，实际CODESYS检查串行；总耗时包括等待、编译、行为测试及主控最后复核。第02/06/09/14题采用题库原定功能块名，而非统一强制Qxx。

DeepSeek采用思考low，Qwen Max关闭思考；每个模型的两框架采用相同选项。Responses适配只重排同次assistant响应的真实commentary/calls/results，不伪造reasoning或工具结果。先执行真实工具链readiness，失败批次只留排障记录，不计正式成绩。实际返回的模型名、token用量、缓存用量、错误和耗时记录在campaign的budget.json。费用按冻结的最高时段官方价格计算上界，只有收到缓存用量才扣除相应差价；缺少usage按完整预留上界记账，不能填0。该数值是实验费用约束和估算，不是账户账单。

预留按输入请求字节数的保守上界和最大输出计；超出剩余预算时拒绝发起请求，预算文件跨run-id保留。本次采用的每百万tokens价格上界为：DeepSeek输入2元、缓存0.04元、输出8元；北京区Qwen Max输入12元、缓存1.5元、输出36元。来源：[DeepSeek](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[Qwen](https://help.aliyun.com/zh/model-studio/qwen3-8-max)。

每次新运行冻结questions.json、test_protocol.json、manifest.json。每题evidence目录保留题面、task.json、agent.log及结果；每次提交的原始字节源码和完整检查在submissions/版本号/。源码SHA从原始字节计算，HTTP链路不改写换行。首稿编译、最后候选编译、行为结果分开统计，格式/提供方/工具错误、超时和平台阻塞也单独保留。测试期改动源文件会使检查器拒绝混用不同指纹，修改后应启动新的协议运行。

Q20采用[逐题规约](PUBLIC20_SPEC.md)中的v2响应窗口：自动动作当拍或下一拍响应，互锁每拍成立；kick持续时间不补充题面未要求的限制。旧pilot和新口径结果在不同目录保存。第18题当前目标缺少已验证VARIANT接口，四组共同预检为platform_blocked，分母仍为20；另报适用子集可作补充，不能用19题替换总分母。

结果入口为 `reports/experiments/four_group_20261028/full_v3/report.md`、`summary.json`与`results.csv`。readiness目录是管线预检，不能混入本次80行正式矩阵。报告中的“通过”仅涉及真实CODESYS编译和有限离线行为；逐题LTL已提供书面规约，尚未调用形式化求解器或在CODESYS运行时/实体PLC执行。

2026-10-28 v3修正：Q04和Q12含补充保持场景的CycleTime等于实际调用间隔，Q04首拍0ms。两个框架都收到时间契约和R4说明；自研另有题目派生TYPE/Q12算法骨架及词法修复，属于被测框架结构，须在报告中披露。历史旧协议结果不改写。接手审计见reports/handoff_audit_20261028/report.md。
