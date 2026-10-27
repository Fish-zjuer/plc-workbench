FUNCTION_BLOCK IPv4Parser
VAR_INPUT
    ipText : STRING(254);
END_VAR
VAR_OUTPUT
    ipValue : UDINT;
END_VAR
VAR
    i : INT;
    segCount : INT;
    segLen : INT;
    digit : BYTE;
    segVal : UDINT;
    result : UDINT;
    segOk : BOOL;
    ok : BOOL;
END_VAR

ok := TRUE;
result := 0;
segCount := 0;
segLen := 0;
segVal := 0;

FOR i := 0 TO 253 DO
    IF ipText[i] = 0 THEN
        EXIT;
    END_IF;

    IF (ipText[i] >= '0') AND (ipText[i] <= '9') THEN
        digit := BYTE_TO_BYTE(ipText[i]) - 48;
        segVal := segVal * 10 + BYTE_TO_UDINT(digit);
        segLen := segLen + 1;
        IF segVal > 255 THEN
            ok := FALSE;
        END_IF;
    ELSIF ipText[i] = '.' THEN
        IF segLen = 0 THEN
            ok := FALSE;
        END_IF;
        IF segCount >= 3 THEN
            ok := FALSE;
        END_IF;
        result := (result * 256) + segVal;
        segCount := segCount + 1;
        segVal := 0;
        segLen := 0;
    ELSE
        ok := FALSE;
    END_IF;
END_FOR

(* last segment *)
IF segLen = 0 THEN
    ok := FALSE;
END_IF;
IF segCount <> 3 THEN
    ok := FALSE;
END_IF;
result := (result * 256) + segVal;

IF ok THEN
    ipValue := result;
ELSE
    ipValue := 0;
END_IF
END_FUNCTION_BLOCK
