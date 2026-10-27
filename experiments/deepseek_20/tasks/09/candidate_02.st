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

(* ---------- 内部：清空缓冲 ---------- *)
FOR nIndex := 1 TO 100 DO
    aBuffer[nIndex] := 0.0;
END_FOR
nCount := 0;
nIndex := 0;
lrSum  := 0.0;

(* ---------- 主体 ---------- *)
IF reset THEN
    (* 复位：清空窗口与输出 *)
    average           := 0.0;
    windowSizeReached := FALSE;
    error             := FALSE;
    status            := E_MovingAverageStatus.E_OK;
ELSIF (windowSize < 1) OR (windowSize > 100) THEN
    (* 窗口设置错误 *)
    average           := 0.0;
    windowSizeReached := FALSE;
    error             := TRUE;
    status            := E_MovingAverageStatus.E_WINDOW;
ELSE
    error  := FALSE;
    status := E_MovingAverageStatus.E_OK;
    (* 本扫描是否取新样本 *)
    IF cyclicExecution OR ((NOT bFirstScan) AND trigger AND (NOT bTriggerPrev)) THEN
        IF nCount >= windowSize THEN
            (* 窗口已满：新值替换最老值 *)
            IF nIndex >= windowSize THEN
                nIndex := 0;
            END_IF
            nIndex := nIndex + 1;
            lrSum := lrSum - aBuffer[nIndex] + value;
            aBuffer[nIndex] := value;
        ELSE
            (* 窗口未满：追加 *)
            IF nIndex >= windowSize THEN
                nIndex := 0;
            END_IF
            nIndex := nIndex + 1;
            aBuffer[nIndex] := value;
            nCount := nCount + 1;
            lrSum := lrSum + value;
        END_IF
    END_IF
    IF nCount > 0 THEN
        average := lrSum / DINT_TO_LREAL(nCount);
    ELSE
        average := 0.0;
    END_IF
    windowSizeReached := (nCount >= windowSize);
END_IF

bTriggerPrev := trigger;
bFirstScan   := FALSE;
END_FUNCTION_BLOCK
