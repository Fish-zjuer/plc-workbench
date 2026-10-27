TYPE E_MovingAverageStatus :
(
    E_OK        := 16#0000,
    E_WINDOW    := 16#8200
);
END_TYPE

FUNCTION_BLOCK MovingAverage
VAR_INPUT
    cyclicExecution  : BOOL;   (* TRUE: 每个扫描周期读取新值并更新平均值；此时 trigger 无效 *)
    trigger          : BOOL;   (* 外部触发，上升沿读取新值并更新 *)
    value            : LREAL;  (* 新读到的数据值 *)
    windowSize       : INT;    (* 窗口宽度，1..100 *)
    reset            : BOOL;   (* TRUE: 复位移动平均计算 *)
END_VAR
VAR_OUTPUT
    average          : LREAL;  (* 移动平均值 *)
    windowSizeReached: BOOL;   (* TRUE: 已填满最大窗口宽度 *)
    error            : BOOL;   (* TRUE: 执行出错 *)
    status           : WORD;   (* 状态码 *)
END_VAR
VAR
    aBuffer        : ARRAY[1..100] OF LREAL;  (* 内部环形缓冲(实现细节) *)
    nCount         : INT := 0;                (* 当前缓冲内有效样本数 *)
    nIndex         : INT := 0;                (* 当前写入位置 *)
    lrSum          : LREAL := 0.0;
    bTriggerPrev   : BOOL := FALSE;
    bFirstScan     : BOOL := TRUE;
END_VAR
VAR CONSTANT
    N_MAX : INT := 100;
END_VAR

(* ---------- 内部：清空缓冲 ---------- *)
METHOD PRIVATE ClearBuffer
VAR
    i : INT;
END_VAR
FOR i := 1 TO N_MAX DO
    aBuffer[i] := 0.0;
END_FOR
nCount := 0;
nIndex := 0;
lrSum  := 0.0;
average := 0.0;
windowSizeReached := FALSE;

(* ---------- 内部：压入一个样本 ---------- *)
METHOD PRIVATE PushValue
VAR_INPUT
    lrValue : LREAL;
END_VAR
VAR
    lrOld : LREAL;
    nWin  : INT;
END_VAR
nWin := windowSize;
IF nWin < 1 THEN
    nWin := 1;
ELSIF nWin > N_MAX THEN
    nWin := N_MAX;
END_IF

IF nCount >= nWin THEN
    (* 窗口已满：新值替换最老值 *)
    IF nIndex >= nWin THEN
        nIndex := 0;
    END_IF
    nIndex := nIndex + 1;
    lrOld := aBuffer[nIndex];
    aBuffer[nIndex] := lrValue;
    lrSum := lrSum - lrOld + lrValue;
ELSE
    (* 窗口未满：追加 *)
    IF nIndex >= nWin THEN
        nIndex := 0;
    END_IF
    nIndex := nIndex + 1;
    aBuffer[nIndex] := lrValue;
    nCount := nCount + 1;
    lrSum := lrSum + lrValue;
END_IF

IF nCount > 0 THEN
    average := lrSum / DINT_TO_LREAL(nCount);
ELSE
    average := 0.0;
END_IF
windowSizeReached := (nCount >= nWin);

(* ---------- 主体 ---------- *)
IF reset THEN
    ClearBuffer();
    nCount := 0;
    nIndex := 0;
    lrSum := 0.0;
    average := 0.0;
    windowSizeReached := FALSE;
ELSE
    IF (windowSize < 1) OR (windowSize > N_MAX) THEN
        error  := TRUE;
        status := E_MovingAverageStatus.E_WINDOW;
        ClearBuffer();
        nCount := 0;
        nIndex := 0;
        lrSum := 0.0;
        average := 0.0;
        windowSizeReached := FALSE;
    ELSE
        error  := FALSE;
        status := E_MovingAverageStatus.E_OK;
        IF cyclicExecution THEN
            PushValue(lrValue := value);
        ELSIF (NOT bFirstScan) AND trigger AND (NOT bTriggerPrev) THEN
            PushValue(lrValue := value);
        END_IF
    END_IF
END_IF

bTriggerPrev := trigger;
bFirstScan   := FALSE;
END_FUNCTION_BLOCK
