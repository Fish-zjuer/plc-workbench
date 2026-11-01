# 数据集说明

`course32.json` 为当前完整题库，包含20道公共题和12道自建题，以及逐题需求、接口、测试、LTL和自建题溯源字段。网页导入与程序内部加载使用同一文件。

| 文件 | 用途 |
|---|---|
| course32.json | 完整32题任务数据 |
| manifest.json | 整体与逐题内容校验，确定数据版本身份 |
| public20_questions.json | 通用PLC接口检查所需的公共原题文本 |
| sources/custom_provenance.json | 自建题来源、改编与审核资料 |

题目顺序为公共题在前、自建题在后。题库整理保留了需求、接口、测试输入、期望输出和LTL的原有内容。

题库修改后需重新生成校验清单并重新执行实验，原运行结果保留其对应的数据版本身份。数据校验命令：

```powershell
.\.venv\Scripts\python.exe scripts/verify_reproduction_data.py
```

LTL的233条原始公式和文字定义保留，增加semantics与execution字段，存放采样含义、辅助命题及独立观察器。导入不自动改写变量引用。30题已有转换定义；开放数组与VARIANT仍需准确平台模型，含浮点的程序也受当前后端限制。详细范围见docs/FORMAL_MAIN_FLOW.md。
