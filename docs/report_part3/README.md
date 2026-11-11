# 第 3 部分报告和英文 PPT

材料对应 Agent 架构设计与展示指标，已根据组员完成的测试/LTL、结果部分及老师原始要求修订。

- 将 `sections/02_architecture.tex` 和 `appendices/d_code_and_evidence.tex` 按原路径复制到组内 report 工程，覆盖对应章节，然后用组内 XeLaTeX 环境编译两次。
- `Agent_Architecture_EN.pptx` 为三页英文 PPT，分别展示轻量 Harness 的设计特性、修复反馈与 LTL 门禁、老师要求的指标。正文、导航和备注均为英文，沿用组内模版及 Times New Roman 字体。
- `Speaker_Notes_EN.md` 提供英文讲稿，三页约需 85–95 秒。放在测试/LTL 部分之后、结果分析之前。

反馈图已按实际控制流更正。编译错误和功能测试失败驱动自动返修，LTL 反例触发 `formal_blocked`，保存轨迹并停止。该策略可由 `tests/test_tia_verification.py` 中现有的返修/形式化阻断回归验证。

PPT 按老师列出的任务组织、上下文管理、工具调用、编译返修和终止条件说明实现。指标页给出首次/最终编译、场景通过、整题通过、界内性质通过和资源消耗，并标明每组 32 题、348 场景、233 性质的分母。

本机缺少组内报告的 TeX Gyre/Fandol 字体。排版检查使用了 Times New Roman、Arial、宋体和微软雅黑替代，交付章节沿用组内主文件的字体设置。其他章节内容由各负责同学继续补齐。

整轮实验数据与复现缺口见 [整合交接](../INTEGRATION_20261111.md)。运行时源码与当前主分支有 12 个内容差异，需要补齐原运行版本才能严格复现。
