# 来源与可重复性

## 作业资料

本任务资料副本位于 `../../../输入/`。原文件保持不变：

- `Final project_CHINESE.docx`：要求和 motor 示例。
- `Final project_ENGLISH.docx`：英文要求。
- `大作业题库json.zip`：公共题 02、06 的需求及接口。
- `大作业题库.pdf`：题库 PDF。

`motor` 是作业示例，`blower` 与 `edges` 是公共题；没有把它们冒充自建题。本轮也没有替组员完成至少十道自建题的任务。

`examples/` 下的正确对照及故障实现均为本轮人工构造的工具自检材料。故障定义可在 `plc_probe/fixtures.py` 与 `examples/manifest.json` 审查。它们与 `experiments/luna/` 下由 GPT-6 Luna 独立生成的程序分开记录。完整套件数据、源代码 SHA256、固定种子和构建日志在报告中留存。

Luna 另完成公共题 09 移动平均、公共题 14 IPv4 解析。原始题面抽取到 `experiments/luna/briefs/`，只添加功能块命名要求，不提供算法答案。使用的是用户明确指定的 `gpt-6-luna` 子代理；首稿阶段要求不读参考实现/测试、不运行编译器。反馈修订仅由 Luna 修改其代码。模型修订实验由主代理串联执行与反馈，不是一个已经接入模型 API、自主运行的完整 agent harness。

## 执行依赖

- 项目：[STruC++](https://github.com/Autonomy-Logic/STruCpp)
- 固定版本：v0.7.0，Windows x64 便携包。
- 发布包：`https://github.com/Autonomy-Logic/STruCpp/releases/download/v0.7.0/strucpp-win32-x64.zip`
- SHA256：`4f97fcacffc3e26622f7b570b533e2ccab2fb6b61442b38c0cfde1d31096767e`。
- 编译器与其标准库、运行时头文件按原发布包保留，存于工作区缓存；其版权与许可证见依赖目录中的 LICENSE、COPYING 及运行时文件声明。
- 原型自研部分：场景组织、独立契约检查、失败序列精简、重放、回归对比、MCP 工具及实验记录。
- 复用部分：ST 前端、代码生成、TON 等标准库、C++ 运行时和 g++。

Windows 原生程序采用静态链接，避免运行环境找不到 MinGW DLL。时间完全由扫描驱动设置，结果不依赖电脑实际运行快慢。

## 接口与平台资料

- [MCP stdio 传输规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [MCP 工具规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [CODESYS 脚本接口](https://content.helpme-codesys.com/en/CODESYS%20Scripting/_cds_access_cds_func_in_python_scripts.html)
- [CODESYS 官方 MCP](https://content.helpme-codesys.com/en/CODESYS%20Development%20System%20MCP%20Server/_idemcp_start_page.html)
- [CODESYS Test Manager](https://content.helpme-codesys.com/en/CODESYS%20Test%20Manager/_tm_f_test_manager.html)
- [PLCVerif 支持语言及调用方式](https://plcverif-oss.gitlab.io/plcverif-docs/userdocs/QuickStart.html)

后两类平台只是后续可接入能力的资料；当前试验没有调用它们。CODESYS 和 PLCVerif 的具体版本、许可证及本地安装可用性需要实际验证。
