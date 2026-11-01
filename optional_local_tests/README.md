# 本地备用测试流程 可删除

这个目录供没有安装 CODESYS 的同学使用。它通过 STruC++ 将 ST 转成 C++，再用 g++ 编译执行，不代表 CODESYS 运行结果。

使用时保留本目录，安装本地 R4 后端，并取消工作台或批量实验中的“使用 CODESYS 编译与仿真测试”。两个框架共用相同的后端选择；结果中标记 `test_backend: optional_local`，CODESYS 编译状态为 `not_executed`。

提交只需要 CODESYS 的代码时，可以整体删除 `optional_local_tests/`。主流程通过延迟加载访问备用代码；删除后，CODESYS 编译、仿真测试和原有 Z3 入口仍可使用。误选备用模式时会明确提示目录缺失，不会回退或报告成功。

`dataset_backend.py` 是迁移前的本地编译与测试执行实现。题库加载、测试判据保留在主程序中，两种后端使用同一套预期值。主程序中的 `local_test_support.py` 只是缺失检测入口，无需删除。

本地安装脚本、结构体/数组备用驱动与编译器补丁都已集中在本目录，包括 backend_r4.py、struct_checks.py、reference_checks.py、duration_checks.py 与 backend_extensions/。安装命令为 `python -m optional_local_tests.backend_r4 build`，随后执行 `activate`。也可运行 `scripts/setup-reproduction.ps1 -WithOptionalLocalTests`。

`plc_probe/` 仍提供主流程共用的错误类型和配置帮助，不要随本目录一起删除。
