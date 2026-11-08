# TIA 32×4：单模型、两框架、两次独立重复

这轮在团队全集 `full-integration-20261108`（`e50d5c3`）上继续，使用 **deepseek-flash**。四组是 `self_r1`、`self_r2`、`codex_r1`、`codex_r2`，32 题共 128 项任务。每次重复从空源码、独立目录开始，采用相同模型与推理设置。它衡量框架差异及重复运行波动，不是两个模型的对照。

网页原有的 self/Codex × 模型 A/B 实验保留原协议；本轮使用单独的命令行入口，避免把同一个模型冒充两个模型。

## 当前进度（2026-11-08）

| 项目 | 本机状态 |
|---|---|
| 团队源码全集 | 已包含 CODESYS、TIA、共享形式化和网页独立审查 |
| 32×4 实验清单 | 已生成；128 项尚未开始，实际模型请求为 0 |
| 实验用 Codex CLI | 已安装固定版本 0.80.0 |
| PLCverif / Java / CBMC | 已安装，真实正负对照已完成，见下文 |
| TIA Portal / PLCSIM / Bridge / 专用模板 | 待本机安装、配置与验收；Siemens 下载需要登录 |
| Git 中的输出 | `outputs/published/` 为公开导出；完整本机运行目录继续留在 `outputs/tia_matrix/` |

团队以前在其他机器完成的 TIA 代表用例报告仍见 [原验收报告](../reports/tia_final_20261104/README.md)，不计为本机本轮 128 项成绩。

本次运行器、公开导出及已有 Campaign/TIA 相关的 29 项自动测试通过；其中运行器执行测试使用模拟执行器，未调用模型或厂商工具。真实形式化工具验收另列于文末。

## 启动

先按 [TIA 配置说明](TIA_VERIFICATION.md) 配好 Bridge、编译模板、PLCSIM Advanced API、S7-1500 仿真模板及形式化工具。API Key 仍通过网页保存到忽略的 `agent_data/`，不写进脚本。

在仓库根目录执行：

```powershell
# 只准备清单、检查配置、导出状态；不调用模型
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tia-matrix.ps1 -PrepareOnly

# 全部 32×4；默认最多两个任务并发，厂商操作仍串行
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tia-matrix.ps1

# 先做单题四次验收
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tia-matrix.ps1 -Ids CUSTOM_09
```

缺少环境或厂商正负编译对照失败时，阻止付费生成。`setup_required` 返回退出码 2 并保留清单，不把 128 个未开始任务记为失败。请先看最新目录的 `SUMMARY.md`、`matrix.json` 和 `results.csv`。

这版没有原地恢复命令；重启会创建新实验目录。中断后已经保存的每题 receipt 保留，未开始项仍为 `not_started`。

## 固定协议和证据

- 题目：`PUBLIC_01..20` 与 `CUSTOM_01..12`，由统一题库载入并冻结快照；不修改题库接口或 LTL 来提高通过率。
- 模型：`deepseek-flash`，开启思考、`reasoning_effort=low`；其余采样、上下文和输出设置取自运行时本机配置并保存公开快照。
- 预算：两框架每题均为 6 个源码版本、24 次模型请求、1800 秒；每个重复单独计量，模型请求按实际服务用量计费。
- 检查：沿用 TIA SCL 生成/修复、Openness 编译、PLCSIM 原生行为测试、共用判卷及 PLCverif/CBMC 有界 LTL 链路。不支持、超时和环境错误保留各自状态。
- 冻结：保存 Git 版本、工作区是否有改动，以及 Python、PowerShell、C# 源文件 SHA256；每项开始前检查源文件是否变化。
- 结果：`matrix.json` 保存总状态，`results.csv` 保存每项编译/行为/形式化状态和请求数；每题 `details/` 保存 receipt、请求响应、候选源码和逐阶段证据。收到 Ctrl+C 时请求取消并等待工作线程保存。

运行器不宣称全部 32 题均受形式化后端支持。原生 VARIANT ABI、实体 PLC 和无限扫描证明仍不在已验收范围。

## 输出如何进入 GitHub

原始输出含厂商工程副本、本机路径和运行配置，继续由 `.gitignore` 忽略。运行器结束或受控中断时，自动导出到 `outputs/published/<实验目录名>/`；这个目录允许 Git 跟踪。**导出后仍须提交、推送 Git，脚本不会自行发布。**

公开副本包含请求/响应、最终及中间 ST/SCL、编译与仿真文字日志、形式化模型和反例；排除厂商工程、虚拟卡、依赖二进制及私有运行目录。API Key、凭据字段和已知本机路径被移除。ST/SCL 保持原始字节，若包含已知 API Key，导出直接拒绝。每份 `PUBLIC_MANIFEST.json` 列出原始/公开 SHA256、是否经过变换以及被排除的文件；已有公开目录不会覆盖。

## 本机形式化正负对照

[完整对照证据](../outputs/published/20261108_formal_toolchain_controls_complete/SUMMARY.md) 使用 CUSTOM_09 的已保存 ST，扫描上界 3、循环展开 16：正常程序 10 条性质均为 `verified`；把初始状态从 0 改为 1 的故障版本检出 P01、P03、P05 的反例。它不请求模型，也没有执行 TIA/PLCSIM。它用于确认本机形式化工具可运行，不计入 128 项成绩。

本机临时目录不可写且项目路径含中文，PowerShell 入口为当前仓库选择一个空闲盘符作为临时路径别名，仅在该进程中设置 TEMP/TMP，退出时释放自己的别名。它不改变目录权限，也不替换已有盘符。

本次工具来自官方渠道，依赖二进制未提交：

| 工具 | 下载来源 | 本次文件 SHA256 |
|---|---|---|
| PLCverif CLI Windows | [CERN CLI 项目及发行链接](https://gitlab.com/plcverif-oss/cern.plcverif.cli) | `2fa54abc70417d10aeab49f64f05675db47089b42dc726e9338f3ab4dce5d35f` |
| Temurin JRE 25.0.5+8 | [Adoptium 发行页](https://github.com/adoptium/temurin25-binaries/releases) | `da78d54a2fcdbba1e92d5e3f07dd30236f96297891c4a21a781c3f38f5c0beae` |
| CBMC 6.11.0 Windows MSI | [CBMC 发行页](https://github.com/diffblue/cbmc/releases/tag/cbmc-6.11.0) | `8dcb29c2e91329898ecde5b79198dad2f4b5ebc5cb6b7d15e892c4fe26c6ea53` |

这些是本次下载件的记录；上游 latest 链接可能变化，复现时核对实际版本及文件摘要。Java 需与实际 PLCverif 包匹配。
