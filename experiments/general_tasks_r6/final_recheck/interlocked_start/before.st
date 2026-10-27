FUNCTION_BLOCK InterlockedStart
VAR_INPUT
    start : BOOL;
    stop : BOOL;
    permit : BOOL;
END_VAR
VAR_OUTPUT
    running : BOOL;
END_VAR
VAR
    previousStart : BOOL := FALSE;
    startRising : BOOL;
END_VAR

startRising := start AND NOT previousStart;
previousStart := start;

IF stop OR NOT permit THEN
    running := FALSE;
ELSIF startRising THEN
    running := TRUE;
END_IF;

END_FUNCTION_BLOCK