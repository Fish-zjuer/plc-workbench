# 公开运行证据

2026-11-11 已核对团队在另一台机器完成的 [TIA 双模型 128 项结果](../tia_32x4_20261108_results/README.md)。本目录以下内容记录本机单模型重复的准备和工具验收。

这里的文件明确允许进入 GitHub。每份快照均有 `PUBLIC_MANIFEST.json`，记录原始/公开 SHA256、文字内容变换及被排除的厂商工程和二进制文件。没有 API Key；原始完整输出留在本机忽略目录。

## 本轮 TIA 32×4

[最近准备状态](2026-11-08_17-22-37_deepseek_flash/SUMMARY.md)：128 项已列出，**0 项完成、0 次模型请求**，等待本机 TIA 安装与配置。四组为 DeepSeek-flash 在 self/Codex 框架各独立重复两次。见 [运行协议](../../docs/TIA_MATRIX_32X4.md)。

17:03、17:16、17:17 的目录是依赖准备过程中的早期检查记录，均未请求模型，不是额外的实验成绩。

## 形式化工具本机验收

[完整正负对照](20261108_formal_toolchain_controls_complete/SUMMARY.md)：正常 CUSTOM_09 ST 的 10 条性质在扫描上界 3 内通过，故意改错版本检出 3 条反例。这是实际 PLCverif/CBMC 执行，未使用 TIA，也不计入 128 项。

`20261108_formal_toolchain_controls` 保存首次临时目录配置失败的记录；`..._workspace_alias` 为使用仓库路径别名后通过的早期导出；`..._complete` 补齐形式化中间模型文件，作为完整证据入口。原始运行未被修改。
