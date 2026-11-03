FUNCTION_BLOCK IPv4Parser
VAR_INPUT
    ipText : STRING(254);
END_VAR
VAR_OUTPUT
    ipValue : UDINT;
END_VAR
VAR
    i : INT;
    n : INT;
    segCount : INT;
    segLen : INT;
    digit : UDINT;
    segVal : UDINT;
    result : UDINT;
    ok : BOOL;
    oneChar : STRING(1);
    isDigit : BOOL;
END_VAR

ok := TRUE;
result := 0;
segCount := 0;
segLen := 0;
segVal := 0;

n := LEN(ipText);
IF n > 254 THEN
    n := 254;
END_IF

FOR i := 0 TO n - 1 DO
    oneChar := MID(ipText, 1, i + 1);
    isDigit := FALSE;
    digit := 0;

    IF oneChar = '0' THEN
        isDigit := TRUE; digit := 0;
    ELSIF oneChar = '1' THEN
        isDigit := TRUE; digit := 1;
    ELSIF oneChar = '2' THEN
        isDigit := TRUE; digit := 2;
    ELSIF oneChar = '3' THEN
        isDigit := TRUE; digit := 3;
    ELSIF oneChar = '4' THEN
        isDigit := TRUE; digit := 4;
    ELSIF oneChar = '5' THEN
        isDigit := TRUE; digit := 5;
    ELSIF oneChar = '6' THEN
        isDigit := TRUE; digit := 6;
    ELSIF oneChar = '7' THEN
        isDigit := TRUE; digit := 7;
    ELSIF oneChar = '8' THEN
        isDigit := TRUE; digit := 8;
    ELSIF oneChar = '9' THEN
        isDigit := TRUE; digit := 9;
    END_IF

    IF isDigit THEN
        segVal := segVal * 10 + digit;
        segLen := segLen + 1;
        IF segVal > 255 THEN
            ok := FALSE;
        END_IF
    ELSIF oneChar = '.' THEN
        IF segLen = 0 THEN
            ok := FALSE;
        END_IF
        IF segCount >= 3 THEN
            ok := FALSE;
        END_IF
        result := (result * 256) + segVal;
        segCount := segCount + 1;
        segVal := 0;
        segLen := 0;
    ELSE
        ok := FALSE;
    END_IF
END_FOR

IF segLen = 0 THEN
    ok := FALSE;
END_IF
IF segCount <> 3 THEN
    ok := FALSE;
END_IF
result := (result * 256) + segVal;

IF ok THEN
    ipValue := result;
ELSE
    ipValue := 0;
END_IF
END_FUNCTION_BLOCK
