# TIA 32×4 实验结果

- 实验：`2026-11-08_18-23-07`，状态 completed，128/128 条；四组各 32 条。
- 开始：2026-11-08T18:23:07.785496+08:00；结束：2026-11-08T17:48:22.071842+00:00；用时：7.42 小时。
- `results.csv`：逐任务状态与摘要；`SUMMARY.md`：项目自动生成的汇总。
- `experiment.json`：配置、汇总、状态计数和运行时冻结的源码哈希。
- `details/tasks.json`：题库快照；`details/vendor_preflight/`：TIA 正负编译对照。
- `tasks/`：128 份完整 receipt、最终代码和 314 次提交的代码与编译、行为及形式化证据。
- 较大的 JSON 使用 gzip 压缩，解压后即原始 JSON；`manifest.json` 同时记录原文和归档文件的 SHA-256。
- 未包含模型请求/响应、CLI 工作目录与临时令牌、TIA 工程副本、工具安装文件及重复日志。完整原始结果保留在本机 `outputs/campaigns/2026-11-08_18-23-07/`。
- 实验使用了本地未提交的源码修改；冻结哈希与本机文件一致，但远程基础提交本身不足以单独复现实验。
- 功能通过与形式化结论分别统计；有界验证只适用于记录的扫描上界和假设。

| 框架 | 模型 | 结束 | TIA 编译通过 | 功能通过 | 有界 LTL 性质通过 |
|---|---|---:|---:|---:|---:|
| self | deepseek-v4.1-flash-1017 | 32 | 29 | 25 | 43/233 |
| self | qwen3.8-flash | 32 | 25 | 21 | 48/233 |
| codex | deepseek-v4.1-flash-1017 | 32 | 26 | 19 | 43/233 |
| codex | qwen3.8-flash | 32 | 24 | 21 | 50/233 |

状态计数：`{"behavior_not_supported": 7, "compile_failed": 3, "error": 5, "fail": 2, "finite_pass": 86, "formal_blocked": 1, "generation_failed": 3, "invalid_candidate": 1, "missing_candidate": 1, "revision_limit": 7, "simulation_error": 5, "timeout": 7}`。
