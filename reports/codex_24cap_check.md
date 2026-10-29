# Codex 在 24 次请求上限下的检查

日期：2026-10-29

## 现有 bank32 weak 结果

- Codex-DeepSeek：20/31
- Codex-Qwen：16/31（Q18 platform_blocked 不计入分母）

非通过中大量为 `model_requests=24` 的 `model_call_limit`，以及 invalid/missing candidate。

## 严格效率 pilot

对 PUBLIC_10 / PUBLIC_14 × DeepSeek / Qwen 使用“只运行 check.ps1、不读生成物/缓存、直接写 candidate”的严格提示，不改变 24 次上限：

| 题 | 模型 | 状态 | 请求数 |
|---|---|---|---:|
| PUBLIC_10 | deepseek-flash | fail | 7 |
| PUBLIC_14 | deepseek-flash | fail | 14 |
| PUBLIC_10 | qwen3.8-flash | fail | 24 |
| PUBLIC_14 | qwen3.8-flash | invalid_candidate | 24 |

## 结论

- DeepSeek 请求数下降但行为仍未通过；Qwen 仍撞 24 次上限或最终候选无效。
- 在不改变 24 次请求上限的前提下，未找到能把 Codex 提升到合理区间的有效配置。
- Codex 支线停止；主表保留原始结果，并把预算耗尽/无效候选单独标注，不当作纯能力差异。
