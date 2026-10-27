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
    PUMP_RUNTIME_ACC  : LTIME;  // 累计有效运行时间（长时类型）
END_VAR
VAR
    rtTimer           : TON;    // 粘度信号去抖计时
    rtCycleNs         : LINT;   // 本周期可累计的纳秒数
    fbInit            : BOOL := FALSE; // 首次调用标志：上电初始化输出
END_VAR
VAR CONSTANT
    MAINT_LIMIT_NS    : LINT := 1800000000000; // 500 小时 = 500*3600*1e9 ns
END_VAR

// ---- 5. 上电初始化：运行输出 OFF、累计时间为零、维护提示 FALSE ----
IF NOT fbInit THEN
    fbInit           := TRUE;
    VFD_RUN          := FALSE;
    PUMP_RUNTIME_ACC := LINT_TO_LTIME(0);
    PUMP_MAINT_DUE   := FALSE;
    rtTimer(IN := FALSE, PT := T#0S);
END_IF;

// ---- 参数合法性：非正 CycleTime 视为无效调用，本周期不累计时间 ----
rtCycleNs := TIME_TO_LINT(CycleTime);   // TIME 底层单位为纳秒
IF rtCycleNs <= 0 THEN
    rtCycleNs := 0;
END_IF;

// ---- 1. 粘度信号去抖：连续 TRUE 达到 DebounceTime 才认可 ----
// VISCOSITY_OK 变 FALSE 时 TON.IN 为 FALSE，Q 立即失效（条件立即失效）
rtTimer(IN := VISCOSITY_OK, PT := DebounceTime);

// ---- 2. 急停优先：急停(FALSE)立即禁止运行并清除未完成的去抖计时 ----
IF NOT PASTE_E_STOP_NC THEN
    rtTimer(IN := FALSE, PT := DebounceTime);   // 复位计时，清除不完全的去抖
    VFD_RUN := FALSE;
ELSE
    IF rtTimer.Q AND VISCOSITY_OK THEN
        VFD_RUN := TRUE;
    ELSE
        VFD_RUN := FALSE;
    END_IF;
END_IF;

// ---- 3. 运行时间累计：仅在实际运行期间按 CycleTime 累加，停止时保持 ----
IF VFD_RUN AND rtCycleNs > 0 THEN
    PUMP_RUNTIME_ACC := PUMP_RUNTIME_ACC + LINT_TO_LTIME(rtCycleNs);
END_IF;

// ---- 4. 维护提示：累计达到 500 小时置位，仅提示，不影响运行与安全许可 ----
IF PUMP_RUNTIME_ACC >= LINT_TO_LTIME(MAINT_LIMIT_NS) THEN
    PUMP_MAINT_DUE := TRUE;
END_IF;

END_FUNCTION_BLOCK
