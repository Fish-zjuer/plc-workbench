FUNCTION_BLOCK Q03
VAR_INPUT
    Value      : REAL;   (* 输入值 *)
    hiLevel    : REAL;   (* 高限报警值 *)
    loLevel    : REAL;   (* 低限报警值 *)
    hystWindow : REAL;   (* 滞环窗口 *)
END_VAR
VAR_OUTPUT
    hiAlarm : BOOL;      (* 高限报警 *)
    loAlarm : BOOL;      (* 低限报警 *)
    error   : BOOL;      (* FALSE: 无错误; TRUE: 执行中出现错误 *)
    status  : WORD;      (* 状态码 *)
END_VAR

(* 参数检查：
   1) loLevel >= hiLevel                    -> status 16#8001，退出
   2) hystWindow >= (hiLevel - loLevel)     -> status 16#8002
   注：hystWindow 为负值在题面未定义，此处按异常处理用 16#8002。 *)

IF loLevel >= hiLevel THEN
    error   := TRUE;
    status  := 16#8001;
    hiAlarm := FALSE;
    loAlarm := FALSE;
    RETURN;
END_IF;

IF (hystWindow < 0.0) OR (hystWindow >= (hiLevel - loLevel)) THEN
    error   := TRUE;
    status  := 16#8002;
    hiAlarm := FALSE;
    loAlarm := FALSE;
    RETURN;
END_IF;

error  := FALSE;
status := 16#0000;

(* 高限滞环：Value > hiLevel 置位，Value < hiLevel - hystWindow 复位 *)
IF Value > hiLevel THEN
    hiAlarm := TRUE;
ELSIF Value < (hiLevel - hystWindow) THEN
    hiAlarm := FALSE;
END_IF;

(* 低限滞环：Value < loLevel 置位，Value > loLevel + hystWindow 复位 *)
IF Value < loLevel THEN
    loAlarm := TRUE;
ELSIF Value > (loLevel + hystWindow) THEN
    loAlarm := FALSE;
END_IF;
