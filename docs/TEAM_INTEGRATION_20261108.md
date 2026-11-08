# 团队全集归档（2026-11-08）

本版是把现有组员成果集中到同一份代码和分发包的整合快照，供团队统一接手与后续验收。它不是已经全部跑完的最终验收版。本次没有新增模型请求、题目实验、开发测试套件或厂商/形式化工具执行。

统一分支：`full-integration-20261108`。合并父节点为 `feature-web-review-20261104@0f9a3eee` 和 `feat/tia-agent-integration@576fa212`；保留两条历史，不覆盖队友原分支。它们共同包含本次盘点的全部11个分支头；机器可读台账见 [TEAM_INTEGRATION_20261108.json](TEAM_INTEGRATION_20261108.json)。

## 为什么前一版没有 TIA

TIA 的 PR #4 合并目标是其自身的 TIA 分支；11月4日独立审查版以 `integration-20261103` 为基础，未合入这条兄弟分支。其代码和验收报告实际已经存在，只是没有汇合成同一个版本。旧分享包的目录白名单还缺 `integrations/` 和 TIA 报告，进一步造成分发不完整。

本次同时解决代码、说明和分享包三处遗漏，采用真实 merge 保留提交来源。

## 分支与贡献台账

| 分支 | 冻结提交 | 成果来源/内容 | 全集处理 |
|---|---|---|---|
| `agent-32-integration` | `7885ef3c` | 早期团队整合：CODESYS主线与32题候选/实测记录 | 已包含，无需重复合并 |
| `agent-codesys-cbmc` | `0cdaaaef` | fal：PLCverif/CBMC、引用建模、08/18观察器与覆盖边界 | 已包含，无需重复合并 |
| `agent-codesys-formal` | `7645b9cf` | 早期通用任务、CODESYS及Z3链 | 已包含，无需重复合并 |
| `agent-general-tasks` | `61cca816` | 早期通用agent、计划/审查/总结压缩 | 已包含，无需重复合并 |
| `agent-iteration` | `e6c0ae92` | Nathan：公共20题 CODESYS agent、对照实验与诊断闭环 | 已包含，无需重复合并 |
| `bank32-v6` | `671f18ca` | Nathan：统一32题、测试/LTL/来源整理及流程收敛 | 已包含，无需重复合并 |
| `feat/tia-agent-integration` | `576fa212` | Hanwen Hu / huharvey：SCL生成修复、Openness编译、PLCSIM行为及共享形式化接入 | 本次合并父节点 |
| `feature-web-review-20261104` | `0f9a3eee` | Fish-zjuer：网页独立对抗审查与源码绑定重放 | 本次合并父节点 |
| `fix-formal-verification` | `cd611874` | Xiu Jiaqing：TON 与 CBMC 兼容性/验证修复 | 已包含，无需重复合并 |
| `integration-20261103` | `ea42b6eb` | Fish-zjuer：可配置模型服务、回归夹具与复现整理 | 已包含，无需重复合并 |
| `main` | `42bdf36b` | 旧发布入口及基础版本 | 已包含，无需重复合并 |

PR #1（Nathan）、#3（模型服务/复现）及 #5（网页审查）的成果通过祖先关系包含；PR #4 的合并产物 `576fa212` 是本次另一父节点。PR #2 已关闭未合并，是被 #4 替代的早期 TIA 实现，只作为[历史提交](https://github.com/Fish-zjuer/plc-workbench/pull/2)留档，避免把旧版逻辑重新覆盖到已验收的新链路上。台账保留所有5个PR的作者、原始头提交、状态与链接。

## 合并后的能力

在 CODESYS 的基础上，完成了 TIA 的 SCL 生成与修复、编译、PLCSIM 行为测试及共享有界形式化接入和代表性用例验收；尚未覆盖全部 32 题、原生 VARIANT ABI、实体 PLC 和无限扫描证明，也没有重写或扩展验证后端本身。

| 组成 | 已放入同一全集的内容 | 当前边界 |
|---|---|---|
| 题库 | 公共20 + 自建12，需求、接口、测试、233条LTL、来源和内容校验 | 数据集存在不等于每个平台均验收32题 |
| 模型服务 | 可配置 Base URL/API Key、A/B模型、请求计量和预算 | 密钥与本机配置不分发 |
| CODESYS | ST生成修复、厂商编译、仿真测试、共享检查链 | 长时序、原生VARIANT等限制见原说明 |
| TIA | Web/CLI/批量平台选择、SCL生成修复、Openness编译、独立PLCSIM运行器 | 代表性题目与显式范围已验收，原生VARIANT未完成 |
| 形式化 | PLCverif/CBMC统一入口、原观察器与引用建模、SCL边界适配 | 有界、受模型/输入域限制；共享后端未因本次整合扩展 |
| 独立审查 | 网页ST审查、独立上下文、建议轨迹两次重放、源码绑定及人工待复核意见 | TIA SCL审查尚未接入，界面和API明确阻止误用 |
| 历史通用agent | `plc_agent/legacy/` 中的计划、模型总结式上下文压缩、任务工具和终端 | 尚未迁移成网页长对话/计划模式 |
| 本地备用 | R4与旧Z3等既有代码、候选夹具和重放脚本 | 本地结果不冒充厂商实测 |

## 验收记录统一索引

所有数字按原提交、后端和执行范围保留；不把这些数字相加为本全集的测试成绩。

| 已有记录 | 原版本/范围 | 入口 |
|---|---|---|
| Nathan的早期CODESYS方案与对照 | 原PR与其提交历史 | [PR #1](https://github.com/Fish-zjuer/plc-workbench/pull/1) |
| R8生成与适应性修复 | 历史32题候选生成/修复、独立审查争议；非首次生成100%准确率 | [原提交报告](https://github.com/Fish-zjuer/plc-workbench/blob/7885ef3c153d53846fed07a1388ec5ecdde385d3/experiments/dataset_r8/report.md) |
| 11月3日本地重放 | R8的32份候选各两遍；每遍348场景、5703扫描、24111断言 | [核验摘要](validation/20261103/audit.json) / [逐题散列](validation/20261103/saved_replay.json) |
| TIA代表性验收 | 15组ST/SCL正负对照一致、8份SCL编译、代表题PLCSIM、08边界域有界检查 | [原报告](../reports/tia_final_20261104/README.md) / [机器汇总](../reports/tia_final_20261104/report.json) |
| 11月4日独立审查 | 两次DeepSeek请求、正/负候选重放；原测试也能检出所植入错误 | [审查说明](WEB_ADVERSARIAL_REVIEW.md) / [历史回归305项记录](validation/20261104/checks.json) |
| 本次全集整理 | 11个分支覆盖核对、6处冲突处理、Python/JS语法、TIA原证据81个文件散列、分发完整性 | [本次台账](TEAM_INTEGRATION_20261108.json) |

TIA报告的“81项自动回归”是队友历史开发检查；本次“81个文件散列”是证据文件完整性，两者不是同一指标。TIA文件按原字节保留，未重新运行，也未重写其结果。

## 本次冲突与分发处理

- `web.py`：保留TIA的目标平台、SCL后缀、推理设置和环境工具；合并ST审查动作/模型配置/回执。TIA审查保持明确未支持。
- `app.js` / `index.html`：保留TIA设置、平台草稿、批量选择、下载和探针；保留ST审查按钮、意见展示和编辑后失效提示。
- `run_output.py`：平台指标及 `.st` / `.scl` 导出与独立审查摘要同时保留。
- README / `.gitattributes`：保留TIA说明和证据逐字节规则，以及独立审查的来源与源码散列规则。
- 分享包新增 `integrations/`（C# Bridge、独立运行器、项目文件和通知辅助源码）与精简TIA验收报告；排除bin/obj等编译产物。

## 团队现在从哪里接手

双击 `start.cmd`，从同一网页选择 CODESYS 或 TIA。历史终端仍用 `python -m plc_agent.legacy`。完整目录解释见 [CODE_GUIDE.md](CODE_GUIDE.md)。Python可用随包校验过的wheels离线安装；CODESYS、TIA/Openness、PLCSIM、PLCverif、Java、CBMC、许可证与工程模板仍按各机配置，不随包提供。

当前原始资料、两平台适配、旧终端、审查、数据、夹具和代表性证据都已归入同一版本。后续先以本全集提交为基线建立合并后验收矩阵，再讨论新增功能和进一步实验；本次停在整合与交付。
