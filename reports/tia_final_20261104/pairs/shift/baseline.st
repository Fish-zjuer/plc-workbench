FUNCTION_BLOCK Edge
VAR_OUTPUT checksum : DWORD; END_VAR
VAR mask : DWORD; bitIndex : INT; END_VAR
checksum := DWORD#0;
FOR bitIndex := 0 TO 31 DO
    mask := SHL(DWORD#1, bitIndex);
    checksum := checksum OR mask;
END_FOR;
END_FUNCTION_BLOCK