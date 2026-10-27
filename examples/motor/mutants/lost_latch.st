(* SYNTHETIC FAULT: lost_latch -- deliberately incorrect. *)
FUNCTION_BLOCK MotorControl
VAR_INPUT
    StartBtn : BOOL;
    StopBtn : BOOL;
    EStop : BOOL;
END_VAR
VAR_OUTPUT
    Motor : BOOL := FALSE;
END_VAR
IF StopBtn OR EStop THEN
    Motor := FALSE;
ELSIF StartBtn THEN
    Motor := TRUE;
ELSE
    Motor := FALSE;
END_IF;
END_FUNCTION_BLOCK
