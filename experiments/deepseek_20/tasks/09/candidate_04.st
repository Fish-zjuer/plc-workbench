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
    status           : WORD;   (* 状态码: 16#0000 正常 / 16#8200 窗口长度错误 *)
END_VAR
VAR
    aBuffer        : ARRAY[1..100] OF LREAL;  (* 内部环形缓冲(实现细节) *)
    nCount         : INT := 0;                (* 当前缓冲内有效样本数 *)
    nIndex         : INT := 0;                (* 当前写入位置 *)
    lrSum          : LREAL := 0.0;            (* 窗口内有效样本之和 *)
    bTriggerPrev   : BOOL := FALSE;           (* 上一扫描的 trigger，用于上升沿 *)
    bFirstScan     : BOOL := TRUE;            (* 首次调用不产生边沿 *)
END_VAR

(* ---------- 主体 ---------- *)
IF reset THEN
    (* 复位：清空窗口与输出 *)
    FOR nIndex := 1 TO 100 DO
        aBuffer[nIndex] := 0.0;
    END_FOR
    nCount            := 0;
    nIndex            := 0;
    lrSum             := 0.0;
    average           := 0.0;
    windowSizeReached := FALSE;
    error             := FALSE;
    status            := 16#0000;
ELSIF (windowSize < 1) OR (windowSize > 100) THEN
    (* 窗口设置错误：清空并输出错误状态 *)
    FOR nIndex := 1 TO 100 DO
        aBuffer[nIndex] := 0.0;
    END_FOR
    nCount            := 0;
    nIndex            := 0;
    lrSum             := 0.0;
    average           := 0.0;
    windowSizeReached := FALSE;
    error             := TRUE;
    status            := 16#8200;
ELSE
    error  := FALSE;
    status := 16#0000;
    (* 本扫描是否取新样本：cyclicExecution 优先，此时 trigger 无效 *)
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
