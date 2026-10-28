# 32题测试用例与LTL规约使用说明

这是一套单独交付的文件。公共20题、自建12题的原题库和PLC Workbench代码均未修改，也没有切换、合并分支。

## 文件怎么用

| 文件 | 用途 |
| --- | --- |
| 公共20题_LTL规约.md / 自建12题_LTL规约.md | 人工审阅公式、变量定义、环境假设及扫描含义 |
| 公共20题_LTL规约.json / 自建12题_LTL规约.json | 带题号、定义和公式的结构化规约，便于后续编写转换器 |
| 逐题LTL/PUBLIC_01.ltl … PUBLIC_20.ltl、CUSTOM_01.ltl … CUSTOM_12.ltl | 单题规约；每个文件用注释携带解释、列出P编号公式 |
| 公共20题_测试用例.json / 自建12题_测试用例.json | 完整输入、预期输出及前置状态，按题号独立存储 |
| 测试用例索引.md | 快速查看每题的用例名称、扫描数和断言数 |
| 检查与来源记录.json | 来源分支的提交、源文件校验值、数据核对范围与结果 |

**这些LTL是带观察器定义的需求规约，不是某个求解器可直接解析的原生脚本。** G/X/F/U、比较、集合、数组和pre等记号均在规约文档说明。自建题的旧公式未直接照搬，已在这份新文件中统一为“本轮输入＋本轮调用后的输出”。现有题库中的草稿保持原样。

若给Agent阅读，可提供对应题目的题面及LTL定义；若给当前Z3分支执行，需要另行把其支持的性质转换进contract.json的properties，并核对ST受支持的类型/语法。浮点、计时器、数组等性质不能因此算作已获证明。测试输入与预期答案应由测试工具保存；正式评估时不要把整个预期答案表当作生成模型的题面。

## 测试记录与输入含义

每组scenario创建新的FB实例。trace中的每行都明确给出该轮全部输入；先赋输入、调用一次FB，再检查expected。expected只列部分输出时，其他输出不在该轮评分。setup也是实际调用，不是随意设置内部状态。

自建题的旧示例会继承未改动的输入；本文件已经展开成完整输入，使用时不用再次猜默认值。新增用例同样展开。time_ms为顺序标签；自建题中的DtMs、DtSec才是算法使用的时间输入，不应把10ms标签误当成DtSec=0.01。数组JSON的首项对应接口声明的下界；例如CabReq首项代表楼层1。

公共题TIME、LTIME和time_ms均以毫秒传输；两个时间戳之间不隐式补跑任何扫描。公共固定数组trace沿用现有桥接方式，例如processSequence[1]与Slab_Fault_History[0]，没有改成新的FB参数。

数值比较：自建题默认绝对容差1e-6；CUSTOM_04长度与直径0.001mm、转速0.01RPM。公共普通trace的REAL用绝对/相对1e-5，LREAL用1e-9；参考适配器内的REAL比较沿用其原判据。整数、位掩码、状态码和BOOL精确比较；不把容差应用于“<=200kg”等输入阈值。

### adapter_format字段

- bank_trace / profile_trace：使用scenarios[].trace，每行time_ms、inputs、expected。profile_trace也保留profile名。invariants中的not_both要求所有扫描都不能同时为真。
- complete_input_trace：自建题完整输入形式，与上述扫描次序相同；phase标注setup/test。
- struct_rows：公共07/17，保留现有struct_checks的rows格式。rows[].inputs是位置数组，顺序见该题field_order.inputs；expected是命名字段。pumpN对应pumpGroup[N]，query对应recipeQueryResult，recipeN对应recipe[N]。第17题initial是调用方预置的10条数据库记录，每条顺序见input_recipe_fields。第07题RunComd沿用调用方状态，只覆写本轮给定的priority/selection。
- analog_reference_rows：公共08。每组给出analog_length/lower与channel_length/lower；每行count、raw、channels。records的位置顺序见channel_field_order。expected是预期channels；raw须完全保持，配置字段及未处理元素也须保持。每行重写调用方给出的数据是此用例的操作，不是FB自行初始化。
- fifo_reference_rows：公共18。kind和capacity指定关联数组类型和容量；每行enqueue/dequeue/reset、item。expected给出elementCount/status与可评分的item；observer_queue_after是独立数学队列，不能拿来要求物理buffer从0开始连续存放。record类型每条为[key,value]。buffer在同一scenario中保持关联，不能每行清空。

原生位置数组沿用现有0/1传输，普通trace的BOOL使用true/false。结构体、开放数组、VARIANT保持原接口语义，没有改成普通值参数冒充原题完成。

### response_windows字段

start_scan/end_scan为从0开始的闭区间索引；只要窗口内至少一轮的输出同时满足该窗口expected即通过。不能要求每轮满足，也不能把不同轮的零散字段拼成一次通过。逐轮expected和invariants另行检查。仅在明确允许的工序响应使用窗口；急停仍是同拍关闭。新增公共19完整序列也使用这个窗口定义，现有普通bank_runner未自动读取该新增协议，需要复用/适配第20题的窗口检查方式。

## 分支对照及尚未消除的限制

- main：现有公共题、专用测试与离线后端。
- agent-iteration：本次公共固定时间判据、20题LTL文档与Q20响应窗口的主要来源。以检查记录中的本地远程引用提交为准，没有联网刷新分支。
- agent-general-tasks：plc-task-v1通用任务契约。
- agent-codesys-formal：包含通用任务分支，增加形式化/CODESYS入口，但未包含迭代分支全部变更。

这里的测试汇总JSON有自己的plc-standalone-tests-v1结构，**不能把整份汇总文件直接当成plc-task-v1上传运行**。这次按要求只交付独立数据和规约，不修改程序去增加导入入口。现有专用适配器可复用对应原生scenarios数据；通用任务入口需要逐题转换。

公共07/08全部结果在VAR_IN_OUT中，通用schema目前要求独立输出；公共14的STRING(254)也不通过其类型字符检查。自建01以及公共12/16的固定数组需要相应数组桥接。第18题的本地PV引用测试不等于CODESYS原生VARIANT兼容验证。

## 已知规则差异（保留原题与原代码，未擅自消除）

1. 公共04/12题面要求CycleTime为正，迭代分支首轮采用CycleTime=0；本文件保留既有实例并标注协议差异。后续接入前需决定首轮是否作为初始化特例。不能静默把它当成题面的无条件要求。
2. 公共04的500小时测试时间戳超过通用schema的1e9ms上限，应使用原有专用适配器，或另行审批修改schema。本次未改上限。
3. 公共12题面要求报警“至少保持500ms”；既有固定用例还检查在指定时刻关闭。这是较强的选定定时器契约，不能无条件用来否决所有满足最短保持的实现。
4. 公共工序题存在当拍/下一拍的解释空间。公共20与新增19明确导出响应窗口；其他旧固定用例保持原判据。LTL更完整，不代表有限测试已覆盖每一条性质。
5. 自建题仍需队员做PLC场景人工复核。数值例子、枚举和状态观察器核对不替代人工审核，更不替代真实ST执行。

## 来源、合成与检查范围

公共用例主要导出本地各分支中既有独立需求判据，不读取候选ST作为答案；补充了15两原料流程、16直接到输出站、19三种自动模式完整八动作。自建用例以原37组为基础，补充权限矩阵、通信饱和/恢复、PI抗饱和、状态转移组合、投票和预算边界等。新增预期由题目对应的算术/状态规则生成，并与已有示例核对；同一观察器生成的数值核对只能证明内部一致性，不能证明观察器本身完全正确。

LTL中的自然语言数学宏均需按文档独立实现为观察器。public LTL来源为迭代分支需求文档，本次修正了单独副本中的移动平均接口名，并补充扫描约定和限制说明；自建12题在单独副本中补全重写。原有数据集内容未修改。

本次没有编译/运行候选ST，没有启动CODESYS、PLCVerif或Z3。检查记录中的passed仅指数据结构、输入完整性、时间戳顺序、自建预期与规则计算的一致性，以及公式括号/条目完整性；不是LTL语法解析成功或性质证明成功。

统计：公共197组/4390轮，自建151组/1313轮；公共148条、自建85条规约。自建预期核对6248项。
