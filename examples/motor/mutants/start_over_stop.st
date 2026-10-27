(* SYNTHETIC FAULT: start_over_stop -- deliberately incorrect. *)
FUNCTION_BLOCK MotorControl
VAR_INPUT
    StartBtn : BOOL;
    StopBtn : BOOL;
    EStop : BOOL;
END_VAR
VAR_OUTPUT
    Motor : BOOL := FALSE;
END_VAR
IF StartBtn THEN
    Motor := TRUE;
ELSIF StopBtn OR EStop THEN
    Motor := FALSE;
END_IF;
END_FUNCTION_BLOCK
