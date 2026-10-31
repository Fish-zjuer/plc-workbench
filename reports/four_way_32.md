# 32题四域汇总（公共20 + 自建12）

口径：每格为 agent 带修复循环后的通过数；Q18 四组均为 platform_blocked。

| 设置 | 公共20 | 自建12 | 合计/31 | Q18 | 非通过明细 |
|---|---:|---:|---:|---|---|
| self-deepseek | 16/19 | 12/12 | 28/31 | platform_blocked | Q05:fail Q08:fail Q10:fail |
| self-qwen | 18/19 | 12/12 | 30/31 | platform_blocked | Q08:compile_error |
| codex-deepseek | 14/19 | 10/12 | 24/31 | platform_blocked | Q08:fail Q10:compile_error Q12:repair_limit Q15:provider_error Q16:runtime_error CUSTOM_03:fail CUSTOM_06:invalid_candidate |
| codex-qwen | 9/19 | 12/12 | 21/31 | platform_blocked | Q02:task_timeout Q04:fail Q05:fail Q09:fail Q10:repair_limit Q14:timeout Q15:provider_error Q16:fail Q19:compile_error Q20:static_error |

## 自建12题逐题状态

| 题 | self-deepseek | self-qwen | codex-deepseek | codex-qwen |
|---|---|---|---|---|
| CUSTOM_01 | pass | finite_pass | pass | pass |
| CUSTOM_02 | pass | finite_pass | pass | pass |
| CUSTOM_03 | pass | finite_pass | fail | pass |
| CUSTOM_04 | pass | finite_pass | pass | pass |
| CUSTOM_05 | pass | finite_pass | pass | pass |
| CUSTOM_06 | pass | finite_pass | invalid_candidate | pass |
| CUSTOM_07 | pass | finite_pass | pass | pass |
| CUSTOM_08 | pass | finite_pass | pass | pass |
| CUSTOM_09 | pass | finite_pass | pass | pass |
| CUSTOM_10 | pass | finite_pass | pass | pass |
| CUSTOM_11 | pass | finite_pass | pass | pass |
| CUSTOM_12 | pass | finite_pass | pass | pass |
