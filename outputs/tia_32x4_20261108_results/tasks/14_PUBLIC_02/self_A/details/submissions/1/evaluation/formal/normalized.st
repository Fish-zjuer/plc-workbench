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
    prevValue : DWORD;
    historyReady : BOOL;
END_VAR

VAR
    tmpRising : DWORD;
    tmpFalling : DWORD;
    i : INT;
    cntRise : INT;
    cntFall : INT;
END_VAR
VAR_INPUT
WBTEMP_0 : DWORD;
WBTEMP_1 : DWORD;
WBTEMP_2 : INT;
WBTEMP_3 : INT;
WBTEMP_4 : INT;
END_VAR


     
tmpRising := WBTEMP_0;
tmpFalling := WBTEMP_1;
i := WBTEMP_2;
cntRise := WBTEMP_3;
cntFall := WBTEMP_4;
    IF NOT historyReady THEN
        prevValue := value;
        risingBits := DWORD#16#0000_0000;
        fallingBits := DWORD#16#0000_0000;
        noOfRisingBits := USINT#0;
        noOfFallingBits := USINT#0;
        hasChanged := FALSE;
        hasRisingEdges := FALSE;
        hasFallingEdges := FALSE;
        historyReady := TRUE;
    ELSE
        tmpRising := value AND (NOT prevValue);
        tmpFalling := prevValue AND (NOT value);

        risingBits := tmpRising;
        fallingBits := tmpFalling;

        cntRise := 0;
        cntFall := 0;
        FOR i := 0 TO 31 DO
            IF (tmpRising AND SHL(DWORD#16#0000_0001, i)) <> DWORD#16#0000_0000 THEN
                cntRise := cntRise + 1;
            END_IF;
            IF (tmpFalling AND SHL(DWORD#16#0000_0001, i)) <> DWORD#16#0000_0000 THEN
                cntFall := cntFall + 1;
            END_IF;
        END_FOR;

        noOfRisingBits := INT_TO_USINT(cntRise);
        noOfFallingBits := INT_TO_USINT(cntFall);

        hasChanged := (value <> prevValue);
        hasRisingEdges := (tmpRising <> DWORD#16#0000_0000);
        hasFallingEdges := (tmpFalling <> DWORD#16#0000_0000);

        prevValue := value;
    END_IF;
END_FUNCTION_BLOCK