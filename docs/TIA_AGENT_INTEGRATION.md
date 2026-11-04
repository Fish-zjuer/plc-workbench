# TIA 工作台入口

工作台单题和批量实验均可选择 TIA Portal / Siemens SCL。作者生成 SCL 后，统一流程执行接口检查、TIA 编译、PLCSIM Advanced 原生测试、冻结判据判定和共享有界形式化检查。编译或行为错误进入预算内修复；环境与工具错误单独处理。

self/Codex、模型选择、请求计量、6 个源码版本、24 次模型请求、1800 秒总预算及结果导出均复用 Trial/Campaign。CODESYS 保留原入口；TIA 使用独立环境配置和 `.scl` 文件。

- [配置与命令行](TIA_VERIFICATION.md)
- [原生运行环境](TIA_NATIVE_ENVIRONMENT.md)
- [SCL 语义适配边界](TIA_ADAPTER_HARDENING.md)
- [基线兼容性复现](TIA_BASELINE_COMPATIBILITY.md)
- [最终验收结果](../reports/tia_final_20261104/README.md)
