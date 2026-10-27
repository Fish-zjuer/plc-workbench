FUNCTION_BLOCK RestartDelay
VAR_INPUT
    request : BOOL;
    inhibit : BOOL;
    delay : TIME;
END_VAR
VAR_OUTPUT
    running : BOOL;
END_VAR
VAR
    timer : TON;
END_VAR

timer(IN := request AND NOT inhibit, PT := delay);
running := timer.Q OR (request AND NOT inhibit AND (delay <= T#0ms));

END_FUNCTION_BLOCK