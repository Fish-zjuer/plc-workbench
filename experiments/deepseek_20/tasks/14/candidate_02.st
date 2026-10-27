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
    ch : BYTE;
    segVal : UDINT;
    result : UDINT;
    ok : BOOL;
END_VAR

ok := TRUE;
result := 0;
segCount := 0;
segLen := 0;
segVal := 0;

FOR i := 0 TO 253 DO
    ch := ipText[i];

    IF ch = 0 THEN
        EXIT;
    END_IF;

    IF (ch >= 48) AND (ch <= 57) THEN
        (* decimal digit: accumulate, reject value > 255 early *)
        segVal := segVal * 10 + BYTE_TO_UDINT(ch - 48);
        segLen := segLen + 1;
        IF segVal > 255 THEN
            ok := FALSE;
        END_IF;
    ELSIF ch = 46 THEN
        (* '.' separator: segment must be nonempty and at most 4 exist *)
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

(* final segment and total segment count *)
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
