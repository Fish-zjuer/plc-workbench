# 独立 Luna 对抗审查实测

状态：本轮完成，待审核。用户追加要求“加一个对抗性审查环节”。

本轮作者为 `/root/luna_st_author`；审查者为另一个上下文的 `/root/luna_adversarial_reviewer`，均选择 `gpt-6-luna`。审查者只收到五题题面、接口域、扫描约定及 `repair_2` 候选源码，没有收到既有测试、监视器或通过结论。主控未改写任何候选 ST。

## 结果

审查者提出 1 项移动平均的需求歧义，没有提出基于明确题意的代码反例。补充要求其检查数值边界、重复调用及错误恢复后，也未新增具体反例。不能由此推断程序正确，或证明对抗审查提高了检出率。

歧义轨迹为触发模式、窗口为 2：

| 扫描 | reset | trigger | value | 执行后行为 |
|---|---|---|---|---|
| 0 | 1 | 0 | 5 | 清空历史 |
| 1 | 1 | 1 | 10 | 再次复位；触发沿被边沿检测器记住，未采样 |
| 2 | 0 | 1 | 20 | 没有新上升沿，不采样；average=0，窗口未满 |

题面没有规定复位与采样同周期时的优先级，也没有要求暂存复位期间的触发沿。原有契约已明确排除这种同时事件，空历史时的 average 也不评分。因此主控裁决为 `needs_requirement_clarification`。精确轨迹在两个新进程中重放，均符合审查者描述，未触发原监视器失败。

五题重新完成普通/针对性/随机测试，仍全部通过。合并状态为 `needs_review`：普通测试通过不掩盖需求歧义。本轮没有确认缺陷，不进行额外 ST 修订。

## 审查输出也需要检查

首次 `proposals.json` 的路径编码损坏，且轨迹输入未放入 `inputs` 对象，在编译前被拒绝。原始文件保留，反馈格式问题后由审查者另写 `proposals_v2.json`，其源码引用从原包程序化提取；没有由主控代写审查内容。

这次格式修正不是代码修复，也不计为程序反例。需求歧义、模型提案错误与候选程序缺陷分开记录。

## 证据

- [独立输入包](round_1/review_packet.json)：五份题面、源码和源码哈希。
- [原始审查提案](round_1/proposals.json) / [格式拒绝记录](round_1/initial_validation.json)。
- [修正后的提案](round_1/proposals_v2.json) / [Luna 审查说明](round_1/review_v2.md)。
- [主控需求裁决](round_1/adjudication.json)。
- [执行摘要](round_1/evaluation.md) / [完整结果](round_1/evaluation.json) / [两次逐扫描执行](round_1/evaluation_evidence/finding_01.json)。
- [普通测试与审查合并记录](../luna/results/repair_2_with_review.md)。
- [工具流程与状态含义](../../docs/ADVERSARIAL_REVIEW.md)。

工具自身 29 项测试通过，覆盖真实人工故障的确认、正确程序反驳假设、需求歧义、判据冲突、源码哈希过期、错误域、格式错误、后端失败和 MCP 接口；人工故障仅用于工具自检。

执行后端为 STruC++ 0.7.0 + g++，未完成 CODESYS 编译或形式化证明。
