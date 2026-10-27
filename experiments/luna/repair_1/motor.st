FUNCTION_BLOCK MotorControl
VAR_INPUT
    StartBtn : BOOL;
    StopBtn  : BOOL;
    EStop    : BOOL;
END_VAR
VAR_OUTPUT
    Motor : BOOL;
END_VAR

(* Stop conditions have priority over a simultaneous start request. *)
IF StopBtn OR EStop THEN
    Motor := FALSE;
ELSIF StartBtn THEN
    Motor := TRUE;
END_IF;
END_FUNCTION_BLOCK
