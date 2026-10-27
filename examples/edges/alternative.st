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
    changedBits : DWORD;
    risingWork : DWORD;
    fallingWork : DWORD;
    bitIndex : INT;
END_VAR
changedBits := value XOR previousValue;
risingBits := changedBits AND value;
fallingBits := changedBits AND previousValue;
hasChanged := changedBits <> DWORD#0;
hasRisingEdges := risingBits <> DWORD#0;
hasFallingEdges := fallingBits <> DWORD#0;
risingWork := risingBits;
fallingWork := fallingBits;
noOfRisingBits := 0;
noOfFallingBits := 0;
FOR bitIndex := 0 TO 31 DO
    IF (risingWork AND DWORD#1) <> DWORD#0 THEN
        noOfRisingBits := noOfRisingBits + 1;
    END_IF;
    IF (fallingWork AND DWORD#1) <> DWORD#0 THEN
        noOfFallingBits := noOfFallingBits + 1;
    END_IF;
    risingWork := SHR(risingWork, 1);
    fallingWork := SHR(fallingWork, 1);
END_FOR;
previousValue := value;
END_FUNCTION_BLOCK
