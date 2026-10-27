// 注意：本文件按 CODESYS 的 IEC 61131-3 语义书写。
// 题面输出 PUMP_RUNTIME_ACC 的类型为 LTIME（64 位长时，纳秒存储）。
// 关键：本后端 TIME_TO_LINT 返回毫秒，故必须先乘 1 000 000 转成纳秒再累计。
FUNCTION_BLOCK Q04
VAR_INPUT
    VISCOSITY_OK      : BOOL;   // 原始粘度信号：在允许范围内为 TRUE
    PASTE_E_STOP_NC   : BOOL;   // 常闭急停回路：TRUE 允许运行，FALSE 表示急停
    DebounceTime      : TIME;   // 粘度信号要求的连续有效时间，必须为正
    CycleTime         : TIME;   // 本次调用实际代表的间隔，必须为正
END_VAR
VAR_OUTPUT
    VFD_RUN           : BOOL;   // 变频驱动运行命令
    PUMP_MAINT_DUE    : BOOL;   // 运行时间达到 500 小时后的维护提示
    PUMP_RUNTIME_ACC  : LTIME;  // 累计有效运行时间（纳秒存储）
END_VAR
VAR
    rtTimer           : TON;    // 粘度信号去抖计时
    rtCycleNs         : LINT;   // 本周期可累计的纳秒数
    rtAccNs           : LINT;   // 累计纳秒数的整数镜像，便于比较
    fbInit            : BOOL := FALSE; // 首次调用标志：上电初始化输出
END_VAR
VAR CONSTANT
    NS_PER_MS         : LINT := 1000000;              // 1 ms = 1e6 ns
    // 500 h = 500 * 3600 s = 1 800 000 s = 1.8e15 ns
    MAINT_LIMIT_NS    : LINT := 1800000000000000;     // 500 h（纳秒）
END_VAR

// ---- 5. 上电初始化：运行输出 OFF、累计时间为零、维护提示 FALSE ----
IF NOT fbInit THEN
    fbInit           := TRUE;
    VFD_RUN          := FALSE;
    PUMP_RUNTIME_ACC := LINT_TO_LTIME(0);
    rtAccNs          := 0;
    PUMP_MAINT_DUE   := FALSE;
    rtTimer(IN := FALSE, PT := T#0S);
END_IF;

// ---- 参数合法性：非正 CycleTime 视为本周期不累计时间 ----
// TIME_TO_LINT 返回毫秒，乘以 1e6 转成纳秒
rtCycleNs := TIME_TO_LINT(CycleTime) * NS_PER_MS;
IF rtCycleNs <= 0 THEN
    rtCycleNs := 0;
END_IF;

// ---- 1/2. 去抖与急停优先 ----
// IN 同时受粘度信号与急停许可约束：
//   VISCOSITY_OK=FALSE      -> Q 立即失效（条件立即废止）
//   PASTE_E_STOP_NC=FALSE   -> 计时立即复位，清除任何未完成的去抖
rtTimer(IN := VISCOSITY_OK AND PASTE_E_STOP_NC, PT := DebounceTime);

VFD_RUN := rtTimer.Q AND VISCOSITY_OK AND PASTE_E_STOP_NC;

// ---- 3. 运行时间累计：仅在实际运行期间按 CycleTime 累加，停止时保持 ----
IF VFD_RUN AND rtCycleNs > 0 THEN
    rtAccNs          := rtAccNs + rtCycleNs;
    PUMP_RUNTIME_ACC := LINT_TO_LTIME(rtAccNs);
END_IF;

// ---- 4. 维护提示：累计达到 500 小时置位，仅提示，不影响运行与安全许可 ----
IF rtAccNs >= MAINT_LIMIT_NS THEN
    PUMP_MAINT_DUE := TRUE;
END_IF;

END_FUNCTION_BLOCK
