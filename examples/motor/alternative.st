FUNCTION_BLOCK MotorControl
VAR_INPUT
    StartBtn : BOOL;
    StopBtn : BOOL;
    EStop : BOOL;
END_VAR
VAR_OUTPUT
    Motor : BOOL := FALSE;
END_VAR
Motor := (Motor OR StartBtn) AND NOT StopBtn AND NOT EStop;
END_FUNCTION_BLOCK
