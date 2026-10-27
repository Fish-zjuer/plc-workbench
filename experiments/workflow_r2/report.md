# PLC专用流程 R2：真实修复与回归

**原20题最终候选从10题通过有限检查，推进到16题通过；剩余4题因后端支持阻塞。** 其中4题是DeepSeek修复代码，2题是新增结构体行为覆盖；不能把这6题都算成模型修复收益。

本轮是从原始最终候选出发的继续修复，不是20次重新独立生成，也没有覆盖原始成绩。

## 实际改变

- 增加程序控制的PLC流程：收集当前源码与同版本证据→模型提案→完整性和接口检查→版本写入→立即编译/测试→按失败约束修复。
- 接入TUI `/solve 05`、CLI `solve 05`，也作为通用agent的`plc_solve_bank`工具提供；计划模式只制定计划，不调用模型或执行。
- 明确任务后收窄工具范围，减少无关环境/接口探测。保留既往反例，格式重试与源码修改分开计数，整个对话与内部流程共享模型请求上限。
- 所有通过结论绑定源码SHA；模型说“已完成”不能盖过失败或源码变化。预算耗尽、网络错误、后端缺失均留档。

## 逐题复评

| 题 | 原始最终状态 | R2状态 | 模型提案请求数 |
|---|---|---|---|
| [01](tasks/01/result.json) | pass | verified | 0 |
| [02](tasks/02/result.json) | pass | verified | 0 |
| [03](tasks/03/result.json) | pass | verified | 0 |
| [04](tasks/04/result.json) | compile_error | backend_ltime_unavailable | 0 |
| [05](tasks/05/result.json) | fail | verified | 3 |
| [06](tasks/06/result.json) | pass | verified | 0 |
| [07](tasks/07/result.json) | behavior_not_supported | verified | 0 |
| [08](tasks/08/result.json) | compile_error | backend_open_array_unavailable | 0 |
| [09](tasks/09/result.json) | pass | verified | 0 |
| [10](tasks/10/result.json) | fail | verified | 3 |
| [11](tasks/11/result.json) | pass | verified | 0 |
| [12](tasks/12/result.json) | compile_error | backend_ltime_unavailable | 0 |
| [13](tasks/13/result.json) | pass | verified | 0 |
| [14](tasks/14/result.json) | compile_error | verified | 2 |
| [15](tasks/15/result.json) | fail | verified | 1 |
| [16](tasks/16/result.json) | pass | verified | 0 |
| [17](tasks/17/result.json) | behavior_not_supported | verified | 0 |
| [18](tasks/18/result.json) | compile_error | backend_variant_unavailable | 2 |
| [19](tasks/19/result.json) | pass | verified | 0 |
| [20](tasks/20/result.json) | pass | verified | 0 |

代码修复：05, 10, 14, 15。新增行为覆盖：07, 17。原来已通过的10题保持通过。
05焊缝报警不结束初始化、10温控冷却不足、14字符串后端兼容问题已通过原判据。15选择了符合当前扫描时序契约的实现；题面允许的扫描延迟仍需明确，不能把这项差异说成已证工业故障。

04/12仍缺少LTIME支持；08仍受开放数组构造/绑定限制；18遇到VARIANT类型支持缺失。后续R3审计另确认18旧候选正文没有访问item/buffer、容量未初始化，数据存取并未完成；不能只归因于后端，详见[后续审计](../memory_r3/report.md)。保留原题类型和方向，没有降级接口来刷通过。

## 回归与独立检查

- 工具完整回归88项通过；核验16份最终源码和项目文件均匹配通过记录，代码及报告未匹配到本机已授权密钥。
- 16题各在两个新执行进程中重放全部现有有限检查，全部通过；每轮共17,492次FB调用。原固定判据文件哈希未变。
- 05/10/14另外加入未提供给修复模型的补充序列：488、640、130个扫描点，共1,258点，各重放两次，均通过。
- 07/17新增固定结构体数组测试，检查优先级选择、只读配置、配方增删改查、容量、重复编号、最低空槽与状态保留；使用显式copy-in/copy-out，未验证引用别名和并发。
- 对4份修订源码另做隔离上下文的对抗审查。7项提案中1项时间结构无效，6项涉及需求歧义；5项可执行提案未见断言差异，另1项出现差异但仍属待澄清时序，不增加确认缺陷数。

## 自然语言入口与推理配置

另外进行了第05题的入口试验，不能省略失败记录：

| 试验 | 流程结果 | 总模型请求 |
|---|---|---|
| [非思考/范围收敛前](natural_language_integration.json) | repair_limit | 9 |
| [非思考/任务范围收敛后](natural_language_integration_focused.json) | repair_limit | 10 |
| [低思考配置](natural_language_integration_thinking.json) | verified | 10 |

同一DeepSeek模型关闭思考时，两次入口试验未完成修复；低思考配置的一次试验在一次源码修改后通过，额外未见输入也重放通过。当前TUI使用这次验证的低思考配置，仍可在模型配置中更换。这几个试验不足以估计总体可靠率，也不证明换配置后稳定成功。

## 花费与边界

R2预检到最终余额检查，账户人民币余额观测减少约 **¥0.20**，包含批测修复、独立审查和入口试验。余额可能有结算延迟或其他并发使用，不是逐请求精确账单；未充值。密钥没有进入代码、报告或模型上下文。

尚未执行CODESYS、形式化求解器或实体PLC。16/20是当前有限检查结果，不是工业正确率。剩余4题需要补齐后端能力；自然语言修复的稳定性也仍需更多独立重复试验。

## 文件

- [R2结果矩阵](results.json)、[原始20题报告](../deepseek_20/report.md)、[源码哈希与两次回放](verification.json)。
- [结构体测试范围](struct_protocol.json)、[补充测试序列](unseen_probe_protocol.json)、[补充测试摘要](unseen_summary.json)。
- [独立审查及执行](independent_reviews.json)、[工具回归日志](regression_tests.log)。
- [最终证据核验](final_validation.json)。模型请求数按逻辑调用计；服务的429/502/503/504错误另有每次最多3次HTTP尝试。
- [架构说明](../../docs/AGENT_ARCHITECTURE.md)、[使用说明](../../AGENT_README.md)。

使用：

```text
/plan
/solve 05
/act
/solve 05
```

```powershell
python -B -m plc_agent solve 05 --mode plan
python -B -m plc_agent solve 05 --mode execute --max-revisions 3
```
