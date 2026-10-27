FUNCTION_BLOCK EdgeDetection
VAR_INPUT
    value : DWORD;
END_VAR
VAR_OUTPUT
    hasChanged       : BOOL;
    hasRisingEdges   : BOOL;
    risingBits       : DWORD;
    noOfRisingBits   : USINT;
    hasFallingEdges  : BOOL;
    fallingBits      : DWORD;
    noOfFallingBits  : USINT;
END_VAR
VAR
    PreviousValue : DWORD := DWORD#0;
    BitIndex      : USINT;
    Mask          : DWORD;
END_VAR

risingBits := value AND NOT PreviousValue;
fallingBits := PreviousValue AND NOT value;
hasChanged := value <> PreviousValue;
hasRisingEdges := risingBits <> DWORD#0;
hasFallingEdges := fallingBits <> DWORD#0;

noOfRisingBits := 0;
noOfFallingBits := 0;
FOR BitIndex := 0 TO 31 DO
    Mask := SHL(DWORD#1, BitIndex);
    IF (risingBits AND Mask) <> DWORD#0 THEN
        noOfRisingBits := noOfRisingBits + 1;
    END_IF;
    IF (fallingBits AND Mask) <> DWORD#0 THEN
        noOfFallingBits := noOfFallingBits + 1;
    END_IF;
END_FOR;

PreviousValue := value;
END_FUNCTION_BLOCK
