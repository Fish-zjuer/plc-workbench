# 32题 v6 2×2 四设置对照（bank32_v6_2x2）

日期：2026-10-29

- 设置：{self, codex} × {deepseek-flash, qwen3.8-flash}，共 32 题 × 4 = 128 次运行
- harness：统一 v6（`plc_agent/bank32_v6.py` 规范化；self 走 `run_self_bank32_v6.py`，codex 走 `run_codex_relay_task.py`）
- 通过口径：self 的 `finite_pass` / codex 的 `pass` 记为通过
- ⚠ `PUBLIC_18` 为 VARIANT 数组队列题，STruC++ 0.7 本地后端不支持 VARIANT 运行时反射/元素读写（见 receipt counterexample），四组均失败 → 另给「除 Q18」的 31 题口径

## 汇总

| 设置 | 公共20 | 公共19 | 自建12 | 合计/32 | 通过率 | 合计/31 | 通过率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| self-deepseek | 15/20 | 15/19 | 12/12 | **27/32** | 84.4% | **27/31** | 87.1% |
| self-qwen | 16/20 | 16/19 | 10/12 | **26/32** | 81.2% | **26/31** | 83.9% |
| codex-deepseek | 11/20 | 11/19 | 10/12 | **21/32** | 65.6% | **21/31** | 67.7% |
| codex-qwen | 13/20 | 13/19 | 9/12 | **22/32** | 68.8% | **22/31** | 71.0% |

## 非通过明细

- **self-deepseek**（5 题）：PUBLIC_04:revision_limit、PUBLIC_08:runtime_error、PUBLIC_10:revision_limit、PUBLIC_12:revision_limit、PUBLIC_18:revision_limit
- **self-qwen**（6 题）：PUBLIC_04:revision_limit、PUBLIC_10:revision_limit、PUBLIC_12:revision_limit、PUBLIC_18:revision_limit、CUSTOM_03:revision_limit、CUSTOM_05:revision_limit
- **codex-deepseek**（11 题）：PUBLIC_04:invalid_candidate、PUBLIC_08:invalid_candidate、PUBLIC_10:fail、PUBLIC_11:fail、PUBLIC_12:invalid_candidate、PUBLIC_14:invalid_candidate、PUBLIC_18:fail、PUBLIC_19:fail、PUBLIC_20:fail、CUSTOM_03:fail、CUSTOM_05:invalid_candidate
- **codex-qwen**（10 题）：PUBLIC_02:fail、PUBLIC_04:invalid_candidate、PUBLIC_05:fail、PUBLIC_10:invalid_candidate、PUBLIC_14:invalid_candidate、PUBLIC_18:invalid_candidate、PUBLIC_19:fail、CUSTOM_03:fail、CUSTOM_05:invalid_candidate、CUSTOM_06:invalid_candidate

## 逐题状态

| 题 | self-deepseek | self-qwen | codex-deepseek | codex-qwen |
|---|---|---|---|---|
| PUBLIC_01 | finite_pass | finite_pass | pass | pass |
| PUBLIC_02 | finite_pass | finite_pass | pass | fail |
| PUBLIC_03 | finite_pass | finite_pass | pass | pass |
| PUBLIC_04 | revision_limit | revision_limit | invalid_candidate | invalid_candidate |
| PUBLIC_05 | finite_pass | finite_pass | pass | fail |
| PUBLIC_06 | finite_pass | finite_pass | pass | pass |
| PUBLIC_07 | finite_pass | finite_pass | pass | pass |
| PUBLIC_08 | runtime_error | finite_pass | invalid_candidate | pass |
| PUBLIC_09 | finite_pass | finite_pass | pass | pass |
| PUBLIC_10 | revision_limit | revision_limit | fail | invalid_candidate |
| PUBLIC_11 | finite_pass | finite_pass | fail | pass |
| PUBLIC_12 | revision_limit | revision_limit | invalid_candidate | pass |
| PUBLIC_13 | finite_pass | finite_pass | pass | pass |
| PUBLIC_14 | finite_pass | finite_pass | invalid_candidate | invalid_candidate |
| PUBLIC_15 | finite_pass | finite_pass | pass | pass |
| PUBLIC_16 | finite_pass | finite_pass | pass | pass |
| PUBLIC_17 | finite_pass | finite_pass | pass | pass |
| PUBLIC_18 | revision_limit | revision_limit | fail | invalid_candidate |
| PUBLIC_19 | finite_pass | finite_pass | fail | fail |
| PUBLIC_20 | finite_pass | finite_pass | fail | pass |
| CUSTOM_01 | finite_pass | finite_pass | pass | pass |
| CUSTOM_02 | finite_pass | finite_pass | pass | pass |
| CUSTOM_03 | finite_pass | revision_limit | fail | fail |
| CUSTOM_04 | finite_pass | finite_pass | pass | pass |
| CUSTOM_05 | finite_pass | revision_limit | invalid_candidate | invalid_candidate |
| CUSTOM_06 | finite_pass | finite_pass | pass | invalid_candidate |
| CUSTOM_07 | finite_pass | finite_pass | pass | pass |
| CUSTOM_08 | finite_pass | finite_pass | pass | pass |
| CUSTOM_09 | finite_pass | finite_pass | pass | pass |
| CUSTOM_10 | finite_pass | finite_pass | pass | pass |
| CUSTOM_11 | finite_pass | finite_pass | pass | pass |
| CUSTOM_12 | finite_pass | finite_pass | pass | pass |

