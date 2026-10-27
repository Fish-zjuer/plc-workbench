(* SYNTHETIC FAULT: latched_changed_flag -- deliberately incorrect. *)
FUNCTION_BLOCK EdgeDetection
VAR_INPUT
    value : DWORD;
END_VAR
VAR_OUTPUT
    hasChanged : BOOL;
    hasRisingEdges : BOOL;
    risingBits : DWORD;
    noOfRisingBits : USINT;
    hasFallingEdges : BOOL;
    fallingBits : DWORD;
    noOfFallingBits : USINT;
END_VAR
VAR
    previousValue : DWORD := DWORD#0;
    bitIndex : INT;
    mask : DWORD;
END_VAR
risingBits := value AND NOT previousValue;
fallingBits := previousValue AND NOT value;
hasChanged := hasChanged OR (value <> previousValue);
hasRisingEdges := risingBits <> DWORD#0;
hasFallingEdges := fallingBits <> DWORD#0;
noOfRisingBits := 0;
noOfFallingBits := 0;
FOR bitIndex := 0 TO 31 DO
    mask := SHL(DWORD#1, bitIndex);
    IF (risingBits AND mask) <> DWORD#0 THEN
        noOfRisingBits := noOfRisingBits + 1;
    END_IF;
    IF (fallingBits AND mask) <> DWORD#0 THEN
        noOfFallingBits := noOfFallingBits + 1;
    END_IF;
END_FOR;
previousValue := value;
END_FUNCTION_BLOCK
