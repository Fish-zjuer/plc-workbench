# 历史终端与开发工具

这里保留旧的通用对话 Agent、Textual 终端界面、旧题库批测与独立任务 CLI。它们不属于当前网页主流程，不需要日常启动。

需要研究或维护旧实现时，使用 `python -m plc_agent.legacy --help`，例如 `python -m plc_agent.legacy ui`。启动脚本也集中在 `scripts/legacy/`。

主应用只需 `start.cmd`。原来的 `python -m plc_agent ui/run/solve/task/dataset` 命令已退出主入口，改在 `plc_agent.legacy` 命名空间下调用。旧工具可能依赖 `optional_local_tests/` 与本地编译器；不会因此让 CODESYS 网页启动依赖这套旧工具。
