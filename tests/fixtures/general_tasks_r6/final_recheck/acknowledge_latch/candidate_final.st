FUNCTION_BLOCK AcknowledgeLatch
VAR_INPUT
    fault : BOOL;
    acknowledge : BOOL;
END_VAR
VAR_OUTPUT
    alarm : BOOL;
END_VAR
VAR
    ackPrev : BOOL;
    ackRising : BOOL;
END_VAR

(* 上升沿检测基于上一扫描的acknowledge值 *)
ackRising := acknowledge AND NOT ackPrev;

(* fault优先：只要故障存在就置位并保持报警 *)
IF fault THEN
    alarm := TRUE;
ELSIF ackRising THEN
    alarm := FALSE;
END_IF;

(* 每个扫描周期无条件更新历史，fault有效期间也更新 *)
ackPrev := acknowledge;

END_FUNCTION_BLOCK