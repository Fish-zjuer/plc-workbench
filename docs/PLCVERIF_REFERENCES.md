# PLCverif 引用模型与 08/18 观察器

扩展位于工作台，没有修改 PLCverif 安装包、用户 ST 源码或冻结题库。它是调用 PLCverif 前后的模型适配模块，不是 dropins 中的 Java 插件。

## 文件

- plc_agent/plcverif_references.py：固定调用方存储、引用别名、原始数组上下界、受检查的 DINT 下标、PV1 元素复制。
- plc_agent/reference_observers.py：08 的逐通道检查，18 的独立数学队列；仅读取公开接口和调用方存储。
- plc_agent/ltl_adapter.py：候选调用展开与扫描采样。
- plc_agent/cbmc_model.py：C 结构体依赖排序、独立观察器挂接、有限扫描监视器。
- plc_agent/plcverif_backend.py：具体形状调度、共享时间预算、逐 case 结果及反例。

## PUBLIC_08

自动读取题库中四种数组形状的元数据，保留各自上下界、不同长度和按相对位置配对的含义。输入数值由独立观察器提供，不读取测试表中的 expected 或候选程序私有变量。

八条原公式分别检查：原始数组保持、所有配置字段保持、未处理/禁用通道保持、错误模式、错误限值、三种换算。错误时还检查输出值保持。模式与限值同时错误时允许 8001 或 8002，避免凭空规定题目未规定的优先级。

网页“模型与环境 → 验证参数 → 08 题数值覆盖范围”提供两种显式选择：

- ieee（默认）：所有 INT 原始值、BOOL 使能、INT 模式、WORD 初始状态；限值和原输出为 [-1000000,1000000] 内的有限 binary32；count 在两数组较短长度以内。宽范围浮点计算可能超时，超时不计通过。这也不是所有 IEEE 位模式的覆盖，因为排除了非有限值和区间外值。
- boundary：原始值来自 {-27648,-1,0,1,27648}；限值按 (扫描号+通道号)%3 在 (73.25,-30.5)、(-30.5,-30.5)、(-30.5,73.25) 之间轮换；原输出为 -700.25。使能、模式、原状态、合法 count 仍为非确定值。这个选项只覆盖明确列出的数值域，不能宣称完整浮点验证。

换算参考使用 binary32、先乘后除的计算顺序，并允许 与现有模拟量测试协议一致的 1e-6*max(1,abs(actual),abs(expected)) 的误差。无效模式和限值都不执行换算。具体值域及算术约定随每个 case 保存。

## PUBLIC_18

检查 DINT、REAL、BOOL、含 DINT key/REAL value 的记录四种元素类型，各有容量 1、2、7，共 12 个组合。调用方 buffer 关联固定，item 使用独立存储。首次 buffer 内容任意，item 每扫描任意，请求/复位是任意 BOOL 序列，约束 enqueue 与 dequeue 不同时为 TRUE。

观察器维护独立的逻辑队列，按请求上升沿和复位优先级更新。它检查计数、状态、item 保持/出队值，并检查实际 buffer 中存在表示整个逻辑队列的环形排列；不读取候选 head/tail，也不要求固定物理起点。REAL 和记录载荷按位比较，包括 NaN 位模式。未使用的 buffer 槽不要求清零。

P01 在首次调用之前检查队列计数为空，避免将合法的首次入队误判为“初始非空”。其他性质在调用结束后采样。这一初始化解释在证据中单独记录。

目前支持项目 PV1 的 PV_COUNT、PV_COMPATIBLE、PV_READ、PV_WRITE，不等于实现 Siemens/CODESYS 原生 VARIANT ABI 或系统函数。读写必须独立赋值给 BOOL 变量，下标为 DINT 变量或整数字面量。先检查范围，失败返回 FALSE 且不写数据，再对有效下标进行类型转换。只实现容量/类型/元素复制，候选 FIFO 算法仍由原始 ST 执行。

扫描上界仍然限制覆盖：例如容量 7 至少要 15 次扫描才能遇到满队列再次入队被拒绝；4 次扫描通过不代表测试了该边界。

## 结果与边界

所有形状共用一版验证的总时间预算；每条性质必须在每个 case 中通过，才记为整题通过。首个源模型反例可以提前停止后续 case；未执行部分不计通过。每个 case 保存模型、输入域、循环上限、域见证和反例；根 formal.json 汇总。

C 导出器目前假设数组从 0 开始，因此扩展使用零基物理存储，并同时转换引用元素、原始上下界查询与普通数组访问。无效原下标返回 -1，保留数组边界检查，避免类型转换把越界下标变成有效下标。结构体按值依赖重新排序，不修改字段和类型。

内部候选循环按形状设置较小展开上限，仍保留展开完整性断言；需要更多迭代的候选会报告不确定，不会误计通过。整体扫描循环仍使用配置的扫描上界。

入口支持一个 FB 加 TYPE，尚不支持辅助 POU、VAR_TEMP/EXTERNAL/GLOBAL、多维数组、动态切换引用、循环内 RETURN、原程序 EXIT/GOTO。普通非循环 RETURN 可提前退出候选调用，观察器照常执行。混合精度常量、未适配函数或库继续报告 unsupported。

冻结题库仍保留 requires_model 声明。只有原公式、接口、存储形状匹配内置观察器时，运行时才解析该依赖；不会只删除阻断或用 TRUE 替换未知要求。原文件和旧实验快照均不修改。

## 自定义固定存储契约

在自定义任务的 ltl.execution 中设置 reference_model：

```json
{
  "reference_model": {
    "version": 1,
    "objects": [{"name": "PVL_Store_Data", "type": "ARRAY[-3..1] OF DINT"}],
    "bindings": {"a": "PVL_Store_Data", "b": "PVL_Store_Data[-3]"}
  }
}
```

a 可为 ARRAY[*] OF DINT，b 为 DINT；或二者都是 VARIANT 并通过 PV1 操作。a 的首元素与 b 共享存储。LOWER_BOUND(a,1)=-3，UPPER_BOUND(a,1)=1。观察器直接访问内部 PVL_Store_Data 时应使用归一化下标 0..4。

自定义存储默认使用 PLCverif 初始值，在扫描之间保留。需要每扫描由环境改变的数据，应通过 execution.entry 明确赋值。自动随机化及上文的独立观察器只适用于经过核对的课程 08/18。

## 复现

示例参考程序在 examples/formal/Q08.st 和 Q18.st。真实工具回归检查正确程序，以及破坏原始数组、配置字段、队列写入、出队复制和空队列状态码的错误版本：

```powershell
python -m scripts.check_course_references --temp-root C:/path/to/ascii-temp
```

默认使用 08 边界值域/3 次扫描、18 全载荷位模式/4 次扫描。可用 --numeric-domain ieee、--fifo-bound 16、--timeout 300 扩大范围，扩大后可能超时。--temp-root 必须是存在且可写的 ASCII 目录；工具从配置或本机路径发现。结果位于 outputs/course-reference-regression/summary.json。

底层别名/PV1 检查：python -m scripts.check_plcverif_references --temp-root C:/path/to/ascii-temp。

本地回归：python -m unittest tests.test_reference_observers tests.test_plcverif_references tests.test_plcverif_st tests.test_plcverif_backend tests.test_cbmc_model tests.test_dataset_formal_flow。

所有结果都是所列输入域、类型、尺寸和扫描范围内的源模型结论，不是无限扫描或厂商语义等价证明。
