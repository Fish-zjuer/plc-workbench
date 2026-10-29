# self bank32 迭代报告（v6.1）

日期：2026-10-29
范围：`experiments/bank32/run_self_bank32_v6.py` + `plc_agent/{bank32,bank32_v6,dataset_workflow}.py`
目标：在不作弊、少做有争议改动的前提下，让 self 的两个设置（deepseek-flash、qwen3.8-flash）稳定达到 **≥29/32**（公共20 + 自建12）。

## 结论

**目标达成。冻结版（代码 HEAD `62be955`，R7/R8 期间未改任何代码）连续两轮：**

| 轮次 | self-deepseek | self-qwen | 公共域 | 自建域 |
|---|---:|---:|---|---|
| R7 | **30/32** | **30/32** | 两者 19/20 | 两者 11/12 |
| R8 | **32/32** | **32/32** | 两者 20/20 | 两者 12/12 |

- 冻结版两轮两个设置均 ≥29/32，最低 30/32；R8 两个设置均为满分。
- R7 的失败题（deepseek PUBLIC_10/CUSTOM_12；qwen PUBLIC_12/CUSTOM_03）在 R8 全部通过 → 模型采样波动，无持续失败。

### 迭代过程（R3–R6，仅作过程记录）

| 轮次 | self-deepseek | self-qwen | 说明 |
|---|---:|---:|---|
| R3 | 32/32 | 29/32 | 无 R4/R6 的 AUTHOR 规则 |
| R4 | 32/32 | 32/32 | 加“同扫描锁存重算” |
| R5 | 31/32 | 29/32 | 仅版本号文案 |
| R6 | 31/32 | 31/32 | 加“小规模选择枚举” |

- R3–R6 均 ≥29/32，但并非同一 prompt 下的重复测量；最终稳定性以 R7/R8 为准。
- 迭代前基线：self-deepseek **27/32**、self-qwen **26/32**。

## 失败根因与修正

失败主要来自 harness 的信息错误与缺失，而不是模型能力。所有修正均为**后端/语言事实**或**通用工程纪律**，不包含题号特判。

| 文件 | 修正 | 解决的题 |
|---|---|---|
| `plc_agent/bank32.py` | `BACKEND_NOTES` 重写：LTIME 是独立时长类型（`LTIME#...`、`TIME_TO_LTIME`）；`ARRAY[*]` 用 `LOWER_BOUND(arr,1)`；STRING 用 `p := ADR(s); p := p+i; ch := p^`；VARIANT 用 `PV_COUNT/PV_COMPATIBLE/PV_READ/PV_WRITE`；`R_TRIG` 每扫描调用；REAL→INT 四舍五入、floor 用 `TRUNC`；`SHL/SHR` 是函数；TON 同扫描喂命令值且先调用再读 Q；上电非默认输出需显式首扫描初始化 | 04/08/10/12/18/14，以及 CUSTOM_03/05 |
| `plc_agent/bank32_v6.py` | 删除错误的 `TYPE LTIME : LINT` 注入与 `TIME_TO_LTIME` → 整数改写；保留 `(LTIME)` 清理与 `LEN` 改名 | 04/12 |
| `plc_agent/dataset_workflow.py` | 候选自身导致的 `runtime_error` 改为可修复；AUTHOR 增加通用纪律：最短保持从触发起算、同扫描锁存更新后重算输出 | 08、10、12 |
| `experiments/bank32/run_self_bank32_v6.py` | 改用共享 `normalize_v6`（此前 runner 内还有一份旧 normalize，会覆盖修正）；删除 runner 内过时的 LTIME/STRING 说明；`agent_error` 自动重试 4 次（15/30/60s）；连续基础设施错误时冷却 60–180s | 全部（稳定性） |
| `experiments/bank32/aggregate_self_bank32_v6.py` | 新增多轮汇总脚本 | 报告 |

### 迭代中发现的三个关键事实

1. **PUBLIC_18 并非平台限制**：后端 `iec_variant.hpp` 提供 `PV_COUNT/PV_COMPATIBLE/PV_READ/PV_WRITE`。补进说明后，两个模型都通过（deepseek 1 次调用，qwen 也通过）。原先“VARIANT 不可解、上限 31/32”的判断作废。
2. **STRING 指针写法**：`(p+i)^` 编译不过；必须是 `p := p+i; ch := p^`。说明按此修正后 PUBLIC_14 稳定。
3. **LTIME**：早期说明“LTIME 是 LINT 别名”是错的；直接赋值 INT/TIME 会编译失败。正确写法是 `LTIME#0ms`/`LTIME#500h` + `TIME_TO_LTIME`。

## 验证

- **快检**：PUBLIC_04/08/10/12、CUSTOM_03/05 两模型全部由失败转为通过；PUBLIC_18 两模型均通过；PUBLIC_14 修正后两模型通过（deepseek 1 次，qwen 3 次）。
- **回归**：现有 53 个原本通过的 `final.st` 在新 `normalize_v6` 下重评，**0 回归**（53/53 仍通过）。
- **完整轮次**：
  - **R7/R8 为冻结版最终数据**（代码 HEAD `62be955`，期间未改代码）：R7 两设置均 30/32，R8 两设置均 32/32。
  - R3–R6 为迭代过程（AUTHOR 规则有微调），仅作记录。
  - 开发轮 r1/r2（旧说明）仅作对照：r1 经基础设施补跑后 deepseek 32/32、qwen 30/32；r2 两模型 31/32（均只差 Q18，旧说明下无法解）。
- **波动题**：冻结版 R7 的失败题（deepseek PUBLIC_10/CUSTOM_12；qwen PUBLIC_12/CUSTOM_03）在 R8 全部通过；无任何题在两轮持续失败。
- **基础设施**：r1 deepseek 遇 15 连 `HTTP 502`、r2 qwen 遇 stream 超时与 SSL EOF；均为 relay/DashScope 瞬时故障，已重试恢复。失败目录保留在 `reports/bank32_v6_iter1_r{1,2}/agent_error_evidence/`。

## 合规与争议点（如实说明）

### 明确没做的

- 未向模型展示完整测试表；`bank32.validate_bank()` 的泄漏检查保持不变。
- 未加入题号/题名/测试时序特判；明确**没有**采用 `run_self_bank32_strong.py` 中 PUBLIC_10 的题号提示。
- 未修改测试、评估器或通过口径；未重跑 `revision_limit` 直到通过，也未挑选轮次。
- R3–R6 全部报告，包括 qwen 的 29/32。

### 既有机制里的灰区（本轮未扩大）

- `dataset_workflow.compact()` 会把第一个失败场景的最多 4 行反例回灌给模型，**这些行包含 `expected` 字段**。因此“expected answers are never shown”只对完整测试表成立，不是零期望值可见。这是 counterexample-guided repair 的既有设计；若规则要求零 oracle 暴露，需要改造 `compact()`（只给 inputs/actual/violations 或纯布尔反馈），会降低成绩。

### 本轮新增内容中，测试驱动的部分

- 后端事实（LTIME/STRING/LOWER_BOUND/VARIANT `PV_*`/TON/R_TRIG/SHL/TRUNC）是读后端头文件 + 小片段编译验证得到的，属于环境事实，但与具体失败题相关。
- AUTHOR 的三条通用纪律（最短保持从触发起算、同扫描锁存重算、小规模选择枚举）是看过具体失败后加的；没有题号，但明显针对失败类型。若评估目标是“固定 prompt 下的模型能力”，这三条是混淆项；若评估目标是“自研 harness 的工程能力”，属于合理迭代。
- 建议做消融：仅保留后端事实与 bug 修复、移除三条 AUTHOR 规则，跑 1–2 轮，量化提示调优的贡献。

### 基础设施重试的预算口径

- `agent_error` 重试会给该题重新开始 24 请求/1800s 预算。R3 qwen PUBLIC_16 重试 1 次后通过；R6 deepseek PUBLIC_10 重试 2 次仍失败。严格按“每题 24 请求”的绝对上限，这两题超出；若规则要求绝对上限，应改为跨重试累计计数或把重试题单独标注。

### 对比口径

- 共享 `BACKEND_NOTES` 变了，旧 2×2 表的 codex 臂未重跑，不能与新 self 数字直接横比。
- Q18 已可解，32 题口径包含它；与旧 31 题口径对比时注意分母变化。

## 复现

```bash
cd "<repo>/plc-workbench-r8"
export PLC_AGENT_HOME='<plc-workbench>/agent_data'
export PYTHONPATH="$PWD"
export CXX='C:\Users\Athan\.cache\plc-workbench-toolchains\mingw64\bin\g++.exe'
export PATH="/c/Users/Athan/.cache/plc-workbench-toolchains/mingw64/bin:<plc-workbench>/.runtime/bin:$PATH"
export BANK32_V6_OUT="$PWD/reports/bank32_v6_iter1_r5/self"
python -X utf8 -B experiments/bank32/run_self_bank32_v6.py deepseek-flash
python -X utf8 -B experiments/bank32/run_self_bank32_v6.py qwen3.8-flash
python experiments/bank32/aggregate_self_bank32_v6.py reports/bank32_v6_iter1_r3/self reports/bank32_v6_iter1_r4/self
```

## 文件与回滚

- 改动前备份：`plc_agent/bank32.py.bak_20261029`、`bank32_v6.py.bak_20261029`、`dataset_workflow.py.bak_20261029`。
- 复核：`git diff -- plc_agent/bank32.py plc_agent/dataset_workflow.py experiments/bank32/run_self_bank32_v6.py`；`bank32_v6.py` 为未跟踪新文件。
- 结果目录：`reports/bank32_v6_iter1_r3/`、`reports/bank32_v6_iter1_r4/`（最终）；`r1/r2` 为开发轮。

## Token 计量（v6.2，2026-10-30 起）

- 流式请求增加 `stream_options: {"include_usage": true}`（self runner 的 `config_for`）；`provider` 原有的 SSE 解析会接收 usage。
- `dataset_workflow.run` 的 receipt 新增：`token_usage`（prompt/completion/total/cost）、`metrics`（逐次调用的 usage/seconds）、`seconds`。
- runner 在基础设施重试时累加 `experiment_token_usage`，包含失败重试的调用。
- deepseek 的 usage 直接带 `cost`；qwen 只有 token 数，成本需按价格表折算。
- 验证（PUBLIC_01，两模型均 `finite_pass`）：deepseek 6390 tokens / $0.000719；qwen 3349 tokens。
- 旧轮次 R3–R8 未记录 token（请求未带 `include_usage`），不影响稳定性结论；从下一次实验开始自动记录。

## 风险与说明

- 模型采样未固定 temperature，仍存在 ±1 题波动；冻结版 R7/R8 已覆盖该波动，两轮均达标（最低 30/32）。
- 旧 2×2 对照表（`reports/four_way_32_v6_2x2.md`）是历史基线；共享说明变更后，codex 臂未重跑，不能与新结果直接横比。
- PUBLIC_18 的 VARIANT 测试仍受后端 `PV_*` 扩展能力约束；当前 r4 后端支持，换后端需重新验证。
