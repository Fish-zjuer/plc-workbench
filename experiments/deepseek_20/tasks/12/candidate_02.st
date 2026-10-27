(*
  公共题库第 12 题：Slab Thickness Alarm and Fault History
  主功能块：Q12
  说明：
    - 保持时间 500 ms 以 TIME 字面量常量（500 ms）比较，不依赖具体任务周期。
    - 上电初始化在首次调用时执行（实例化即视为上电）。
    - 输出 Slab_Fault_History 由 FB 内部私有缓冲拷出，调用方只能读取，
      无法修改内部记录，满足“只读”要求。
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
    holdTimer              : LTIME;                (* 报警保持计时 *)
    alarmLatched           : BOOL;                 (* 报警锁存状态 *)
    runtimeSum             : LTIME;                (* 正常切割时间累加 *)
    historyBuf             : ARRAY[0..4] OF DINT; (* 内部故障历史缓冲，索引 0 最新 *)
    i                      : INT;                  (* 循环变量 *)
END_VAR

(* ---------- 上电初始化（仅首次调用执行） ---------- *)
IF NOT initDone THEN
    initDone := TRUE;
    THICKNESS_ALARM := FALSE;
    alarmLatched := FALSE;
    holdTimer := LTIME#0MS;
    lastValidFault := FALSE;
    Slab_Fault_Counter := 0;
    runtimeSum := LTIME#0MS;
    FOR i := 0 TO 4 DO
        historyBuf[i] := 0;
        Slab_Fault_History[i] := 0;
    END_FOR
END_IF

(* ---------- 有效故障状态 ---------- *)
(* 仅当信号有效时才把 THICKNESS_FAULT 视为有效故障 *)
IF THICKNESS_SIGNAL_VALID AND THICKNESS_FAULT THEN
    (* 报警立即置位并锁存，保持至少 500 ms *)
    THICKNESS_ALARM := TRUE;
    alarmLatched := TRUE;

    (* 有效故障上升沿：计数 +1，历史移位，新记录进 0 号 *)
    IF NOT lastValidFault THEN
        IF Slab_Fault_Counter < 65535 THEN
            Slab_Fault_Counter := Slab_Fault_Counter + 1;
        END_IF
        FOR i := 4 TO 1 BY -1 DO
            historyBuf[i] := historyBuf[i - 1];
        END_FOR
        historyBuf[0] := FaultTimestamp;
    END_IF
    lastValidFault := TRUE;
ELSE
    lastValidFault := FALSE;
END_IF

(* ---------- 报警最小保持 500 ms ---------- *)
IF alarmLatched THEN
    IF NOT THICKNESS_SIGNAL_VALID THEN
        (* 信号无效：立即关断报警并清除保持状态 *)
        holdTimer := LTIME#0MS;
        alarmLatched := FALSE;
        THICKNESS_ALARM := FALSE;
    ELSIF THICKNESS_FAULT THEN
        (* 故障持续：保持计时清零，报警一直有效 *)
        holdTimer := LTIME#0MS;
        THICKNESS_ALARM := TRUE;
    ELSE
        (* 故障撤销：累积保持时间，满 500 ms 后释放 *)
        IF CycleTime > T#0S THEN
            holdTimer := holdTimer + TIME_TO_LTIME(CycleTime);
        END_IF
        IF holdTimer >= LTIME#500MS THEN
            holdTimer := LTIME#0MS;
            alarmLatched := FALSE;
            THICKNESS_ALARM := FALSE;
        ELSE
            THICKNESS_ALARM := TRUE;
        END_IF
    END_IF
ELSE
    holdTimer := LTIME#0MS;
    THICKNESS_ALARM := FALSE;
END_IF

(* ---------- 正常切割运行时间累加 ---------- *)
IF CUTTING_RUN AND THICKNESS_SIGNAL_VALID AND NOT THICKNESS_FAULT THEN
    IF CycleTime > T#0S THEN
        runtimeSum := runtimeSum + TIME_TO_LTIME(CycleTime);
    END_IF
END_IF
(* 否则保留原累计值 *)

(* ---------- 输出刷新 ---------- *)
Slab_Runtime_Accumulator := runtimeSum;
FOR i := 0 TO 4 DO
    Slab_Fault_History[i] := historyBuf[i];
END_FOR
