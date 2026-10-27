(* SYNTHETIC FAULT: ignore_estop -- deliberately incorrect. *)
FUNCTION_BLOCK MotorControl
VAR_INPUT
    StartBtn : BOOL;
    StopBtn : BOOL;
    EStop : BOOL;
END_VAR
VAR_OUTPUT
    Motor : BOOL := FALSE;
END_VAR
IF StopBtn THEN
    Motor := FALSE;
ELSIF StartBtn THEN
    Motor := TRUE;
END_IF;
END_FUNCTION_BLOCK
