(*
  公共题库第 12 题：Slab Thickness Alarm and Fault History
  主功能块：Q12

  实现说明：
    - 有效故障上升沿：计数、历史移位，并在同一扫描内复位并重新启动 500 ms 保持定时器。
    - 报警在故障持续期间保持；故障撤销后至少保持 500 ms。
    - 信号无效时立即关闭报警并清除保持状态。
    - 正常切割运行时间内部用 LTIME 累加。
    - Slab_Fault_History 由内部私有缓冲刷新到输出，避免调用方修改内部历史。
*)
FUNCTION_BLOCK Q12
VAR_INPUT
    THICKNESS_FAULT        : BOOL;   (* 厚度偏差超差 *)
    THICKNESS_SIGNAL_VALID : BOOL;   (* 厚度信号有效 *)
    CUTTING_RUN            : BOOL;   (* 切割设备运行中 *)
    FaultTimestamp         : DINT;   (* 当前时间戳（秒），故障记录标识 *)
    CycleTime              : TIME;   (* 本次调用代表的实际间隔，应为正 *)
END_VAR
VAR_OUTPUT
    THICKNESS_ALARM        : BOOL;                 (* 厚度报警，最小保持 500 ms *)
    Slab_Fault_Counter     : UINT;                 (* 有效厚度故障发生次数 *)
    Slab_Runtime_Accumulator : LTIME;              (* 正常切割累计运行时间 *)
    Slab_Fault_History     : ARRAY[0..4] OF DINT; (* 最近 5 次故障时间戳，0 为最新 *)
END_VAR
VAR
    initDone               : BOOL;                 (* 上电初始化标志 *)
    lastValidFault         : BOOL;                 (* 上一次扫描的有效故障状态（上升沿检测） *)
    alarmLatched           : BOOL;                 (* 报警锁存状态 *)
    holdRestart            : BOOL;                 (* 本扫描需要复位并重启保持定时器 *)
    holdTonic              : TON;                  (* 500 ms 最小保持定时器 *)
    runtimeSum             : LTIME;                (* 正常切割时间累加 *)
    historyBuf             : ARRAY[0..4] OF DINT; (* 内部故障历史缓冲，索引 0 最新 *)
    i                      : INT;                  (* 循环变量 *)
END_VAR

(* ---------- 上电初始化（仅首次调用执行） ---------- *)
IF NOT initDone THEN
    initDone := TRUE;
    THICKNESS_ALARM := FALSE;
    alarmLatched := FALSE;
    lastValidFault := FALSE;
    holdRestart := FALSE;
    Slab_Fault_Counter := 0;
    runtimeSum := TIME_TO_LTIME(T#0S);
    FOR i := 0 TO 4 DO
        historyBuf[i] := 0;
        Slab_Fault_History[i] := 0;
    END_FOR
END_IF

(* ---------- 有效故障状态、计数、历史与报警触发 ---------- *)
IF NOT THICKNESS_SIGNAL_VALID THEN
    (* 信号无效：立即清除报警与保持状态，不计故障、不累加正常时间 *)
    alarmLatched := FALSE;
    THICKNESS_ALARM := FALSE;
    holdRestart := FALSE;
    lastValidFault := FALSE;
ELSE
    IF THICKNESS_FAULT THEN
        (* 有效故障上升沿：计数 +1，历史移位，新记录进 0 号 *)
        IF NOT lastValidFault THEN
            IF Slab_Fault_Counter < 65535 THEN
                Slab_Fault_Counter := Slab_Fault_Counter + 1;
            END_IF
            FOR i := 4 TO 1 BY -1 DO
                historyBuf[i] := historyBuf[i - 1];
            END_FOR
            historyBuf[0] := FaultTimestamp;

            (* 每个有效故障都从自己的触发扫描开始重新计算 500 ms 最小保持 *)
            holdRestart := TRUE;
        END_IF
        lastValidFault := TRUE;
        alarmLatched := TRUE;
        THICKNESS_ALARM := TRUE;
    ELSE
        lastValidFault := FALSE;
        (* 故障撤销后，报警由保持定时器决定是否释放 *)
    END_IF
END_IF

(* ---------- 报警最小保持 500 ms ---------- *)
(* 在触发扫描内先复位 TON，再立即以 IN=TRUE 调用，使计时从本扫描开始。 *)
IF holdRestart THEN
    holdTonic(IN := FALSE, PT := T#500MS);
    holdRestart := FALSE;
END_IF
holdTonic(IN := alarmLatched, PT := T#500MS);

(* ---------- 报警释放条件 ---------- *)
IF alarmLatched AND THICKNESS_SIGNAL_VALID THEN
    IF NOT THICKNESS_FAULT AND holdTonic.Q THEN
        (* 故障已撤销且本次触发后已满 500 ms，释放报警 *)
        alarmLatched := FALSE;
        THICKNESS_ALARM := FALSE;
    ELSE
        (* 故障仍存在或保持时间未满，报警继续有效 *)
        THICKNESS_ALARM := TRUE;
    END_IF
ELSIF NOT THICKNESS_SIGNAL_VALID THEN
    THICKNESS_ALARM := FALSE;
ELSE
    THICKNESS_ALARM := FALSE;
END_IF

(* ---------- 正常切割运行时间累加 ---------- *)
(* 仅当 CUTTING_RUN=TRUE、信号有效且无厚度故障时累加，否则保留原值 *)
IF CUTTING_RUN AND THICKNESS_SIGNAL_VALID AND NOT THICKNESS_FAULT THEN
    IF CycleTime > T#0S THEN
        runtimeSum := runtimeSum + TIME_TO_LTIME(CycleTime);
    END_IF
END_IF

(* ---------- 输出刷新 ---------- *)
Slab_Runtime_Accumulator := runtimeSum;
FOR i := 0 TO 4 DO
    Slab_Fault_History[i] := historyBuf[i];
END_FOR

END_FUNCTION_BLOCK