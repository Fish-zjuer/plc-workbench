# 当前契约、采样与规约

此文件定义原型的判定范围。下面的 LTL 用于说明性质，**本轮没有调用 LTL 求解器或声称完成形式化验证**。真正执行的是 Python 逐扫描监视器。

## 统一采样约定

每行 `time_ms` 为一次功能块调用开始时的虚拟时刻。该行的 `inputs` 是本轮输入；`actual` 是本轮执行完的输出。相邻采样点间输入保持不变。每条场景从全新的 FB 实例开始；不模拟 RETAIN、掉电或真实硬件复位。

时间严格递增，范围 0..86400000 ms。每条场景最多 10000 轮，每批最多 250000 轮。执行有独立超时；超时属于工具状态，不属于性质通过。每条场景必须给齐接口输入。

时间比较使用 STruC++ 自带运行时的虚拟扫描时钟；实际 TON 实现由随编译器发布的标准功能块提供。本工具没有另写一个候选程序的 Python 仿真版本代替执行。不同 PLC 平台的计时语义仍须在 CODESYS 上交叉核对。

本文件的 LTL 以“输入 + 本轮输出”为一个观测状态，因此同周期要求不用 `X`。作业示例把输入/下一状态写为 `X Motor`，属于另一种采样约定；两种约定不能混用。

## motor：作业文档中的电机启停示例

输入 `StartBtn`、`StopBtn`、`EStop`，输出 `Motor`。EStop=TRUE 表示急停有效。初始 Motor=FALSE；停止/急停优先；启动后松开按钮保持运行。

```text
初始：!Motor
G((StopBtn | EStop) -> !Motor)
G((StartBtn & !StopBtn & !EStop) -> Motor)
G((Motor & X(!StopBtn & !EStop)) -> X(Motor))
```

接口见 `examples/motor/correct.st`。这来自作业示例，**不能计作自建题**。

## blower：公共题 06

输入 `DO_LOW`、`AERATION_E_STOP_NC`；后者 TRUE 才允许运行。条件连续有效 5000 ms 后启动；任一条件失效时本轮关闭输出并清除计时；恢复必须重新等待。只在运行指令上升沿增加一次 UINT 计数。

观察器 `eligible = DO_LOW & AERATION_E_STOP_NC`；`ready` 表示从最近一次连续 eligible 的首个采样点开始，已过去至少 5000 ms。首次 eligible 的那轮 elapsed=0。`rose_run` 是用上一轮输出定义的辅助观察量。

```text
初始：!BLOWER_RUN & count=0
G(BLOWER_RUN -> eligible)
G(BLOWER_RUN -> ready)
G((eligible & ready) -> BLOWER_RUN)
G((!eligible) -> (!BLOWER_RUN & !ready))
G(rose_run -> count = previous_count + 1)
G((!rose_run) -> count = previous_count)
```

辅助观察器只是把时长、上一轮值等信息显式表示；LTL 的 `X` 本身不代表“一毫秒”或“一秒”。当前试验不涉及计数溢出；监视器按 UINT 取模存储，不据此补充题面未定义的工业溢出策略。

## edges：公共题 02

输入为 32 位无符号 DWORD。上一轮输入为 `previous_value`：

```text
rising_mask  = value & ~previous_value & 0xFFFFFFFF
falling_mask = previous_value & ~value & 0xFFFFFFFF
G(risingBits = rising_mask)
G(fallingBits = falling_mask)
G(noOfRisingBits = popcount(rising_mask))
G(noOfFallingBits = popcount(falling_mask))
G(hasChanged = (value != previous_value))
G(hasRisingEdges = (rising_mask != 0))
G(hasFallingEdges = (falling_mask != 0))
```

题面没有定义第一次调用的历史值策略，因此**首轮仅建立历史，不判输出对错**。其后每轮必须精确匹配。代码风格不同并不影响契约。

## moving_average：公共题 09

合法窗口为 1..100；周期模式每轮采样；触发模式只在 trigger 上升沿采样。以最近不超过窗口大小的已采集样本，用独立的 `math.fsum` 重新计算均值。LREAL 使用绝对/相对 1e-9 容差。非法窗口检查 error 与 16#8200，正常执行检查无错与 16#0000。

每个实例内窗口固定；本轮不判定动态改变窗口后的历史处理策略。reset 场景不同时请求采样，不替题目裁定重置与采样同周期的细节。没有样本时不判定 average 数值。输入浮点数必须有限。

## ipv4：公共题 14

按题面检查四段非空十进制字符、每段 0..255、网络字节序；非法文本结果为零，并在有效地址后立即输入非法文本，检查是否错误保留旧输出。输入仅限长度不超过 254 的可打印 ASCII；其他编码与控制字符由接口拒绝，不声称已覆盖。

含前导零的三位字段按题面数字规则解释。当前生成场景没有评价超过 15 字符、但各段仍因大量前导零而数值有效的特殊形式；不据此裁定模型采用 15 字符限制是否完全符合题意。

## 为什么还不能外推到全部 PLC

当前只处理单个 FB 的顺序调用，预期值检查覆盖五个明确定义的接口。没有物理被控对象、多任务调度、现场总线、传感器失效诊断或硬件功能安全结论。`pass` 的含义仅是“本次有限场景集没有发现违反当前契约的行为”。

对于停机后是否允许自动恢复、模式切换应保留哪些状态等问题，本原型不会擅自决定；必须有独立、明确的任务契约后才能增加对应检查。
