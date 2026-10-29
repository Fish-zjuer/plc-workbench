# 32题四域表（weak harness，bank32）

口径：Q18 四组 platform_blocked；可做 31 题（公共19 + 自建12）。

| 设置 | 公共19 | 自建12 | 合计/31 | 通过率 | 非通过 |
|---|---:|---:|---:|---:|---|
| self-deepseek | 14/19 | 12/12 | **26/31** | 83.9% | PUBLIC_04:revision_limit PUBLIC_08:revision_limit PUBLIC_10:revision_limit PUBLIC_12:revision_limit PUBLIC_14:revision_limit |
| self-qwen | 14/19 | 12/12 | **26/31** | 83.9% | PUBLIC_04:revision_limit PUBLIC_08:revision_limit PUBLIC_10:revision_limit PUBLIC_12:agent_error PUBLIC_14:revision_limit |
| codex-deepseek | 9/19 | 11/12 | **20/31** | 64.5% | PUBLIC_02:missing_candidate PUBLIC_05:fail PUBLIC_07:fail PUBLIC_08:invalid_candidate PUBLIC_09:fail PUBLIC_10:fail PUBLIC_12:fail PUBLIC_14:fail PUBLIC_16:fail PUBLIC_19:invalid_candidate CUSTOM_03:fail |
| codex-qwen | 9/19 | 7/12 | **16/31** | 51.6% | PUBLIC_04:fail PUBLIC_05:fail PUBLIC_06:invalid_candidate PUBLIC_10:fail PUBLIC_11:fail PUBLIC_12:fail PUBLIC_13:fail PUBLIC_14:fail PUBLIC_19:fail PUBLIC_20:fail CUSTOM_01:fail CUSTOM_03:fail CUSTOM_10:fail CUSTOM_11:invalid_candidate CUSTOM_12:fail |

## 逐题状态（weak）

| 题 | self-deepseek | self-qwen | codex-deepseek | codex-qwen |
|---|---|---|---|---|
| PUBLIC_01 | finite_pass | finite_pass | pass | pass |
| PUBLIC_02 | finite_pass | finite_pass | missing_candidate | pass |
| PUBLIC_03 | finite_pass | finite_pass | pass | pass |
| PUBLIC_04 | revision_limit | revision_limit | pass | fail |
| PUBLIC_05 | finite_pass | finite_pass | fail | fail |
| PUBLIC_06 | finite_pass | finite_pass | pass | invalid_candidate |
| PUBLIC_07 | finite_pass | finite_pass | fail | pass |
| PUBLIC_08 | revision_limit | revision_limit | invalid_candidate | pass |
| PUBLIC_09 | finite_pass | finite_pass | fail | pass |
| PUBLIC_10 | revision_limit | revision_limit | fail | fail |
| PUBLIC_11 | finite_pass | finite_pass | pass | fail |
| PUBLIC_12 | revision_limit | agent_error | fail | fail |
| PUBLIC_13 | finite_pass | finite_pass | pass | fail |
| PUBLIC_14 | revision_limit | revision_limit | fail | fail |
| PUBLIC_15 | finite_pass | finite_pass | pass | pass |
| PUBLIC_16 | finite_pass | finite_pass | fail | pass |
| PUBLIC_17 | finite_pass | finite_pass | pass | pass |
| PUBLIC_18 | platform_blocked | platform_blocked | platform_blocked | platform_blocked |
| PUBLIC_19 | finite_pass | finite_pass | invalid_candidate | fail |
| PUBLIC_20 | finite_pass | finite_pass | pass | fail |
| CUSTOM_01 | finite_pass | finite_pass | pass | fail |
| CUSTOM_02 | finite_pass | finite_pass | pass | pass |
| CUSTOM_03 | finite_pass | finite_pass | fail | fail |
| CUSTOM_04 | finite_pass | finite_pass | pass | pass |
| CUSTOM_05 | finite_pass | finite_pass | pass | pass |
| CUSTOM_06 | finite_pass | finite_pass | pass | pass |
| CUSTOM_07 | finite_pass | finite_pass | pass | pass |
| CUSTOM_08 | finite_pass | finite_pass | pass | pass |
| CUSTOM_09 | finite_pass | finite_pass | pass | pass |
| CUSTOM_10 | finite_pass | finite_pass | pass | fail |
| CUSTOM_11 | finite_pass | finite_pass | pass | invalid_candidate |
| CUSTOM_12 | finite_pass | finite_pass | pass | fail |

## Harness 消融（self-Qwen，31 题口径）

| harness | 公共19 | 自建12 | 合计/31 |
|---|---:|---:|---:|
| weak | 14/19 | 12/12 | 26/31 |
| strong | 11/19 | 11/12 | 22/31 |

## Token / 请求消耗（32 题）

| 设置 | 任务 | 模型请求 | 输入 tokens | 输出 tokens | 总 tokens | 平均输入/题 | 平均输出/题 |
|---|---:|---:|---:|---:|---:|---:|---:|
| self-deepseek | 32 | 74 | — | — | — | — | — |
| self-qwen | 32 | 60 | 174,403 | 79,764 | 254,167 | 5,450 | 2,493 |
| codex-deepseek | 32 | 526 | 7,979,127 | 152,889 | 8,132,016 | 249,348 | 4,778 |
| codex-qwen | 32 | 691 | 9,921,341 | 134,920 | 10,056,261 | 310,042 | 4,216 |

说明：
- self-deepseek 的 provider 没有返回 usage，只能记录请求数。
- self-qwen 缓存输入 39,680 tokens；codex receipt 未单独拆出缓存 tokens。
- 请求数来自 self receipt 的 model_calls 和 codex receipt 的 model_requests。
- 这是修复循环的总消耗，不是单次生成的消耗。
