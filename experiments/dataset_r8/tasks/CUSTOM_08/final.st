FUNCTION_BLOCK FB_CraneSpeedCheck
VAR_INPUT
    LeftSpeed10      : INT;
    RightSpeed10     : INT;
    ReferenceSpeed10 : INT;
END_VAR

VAR_OUTPUT
    SyncOK  : BOOL;
    SyncBad : BOOL;
    Invalid : BOOL;
END_VAR

VAR
    Valid     : BOOL;
    LVal      : DINT;
    RVal      : DINT;
    RefVal    : DINT;
    DiffLR    : DINT;
    DiffSum   : DINT;
    SumLR     : DINT;
    TargetVal : DINT;
END_VAR

// Default: all outputs FALSE; exactly one TRUE is set below each scan
SyncOK  := FALSE;
SyncBad := FALSE;
Invalid := FALSE;

// Range validation before any subtraction or multiplication
Valid := (LeftSpeed10 >= 0) AND (LeftSpeed10 <= 100)
         AND (RightSpeed10 >= 0) AND (RightSpeed10 <= 100)
         AND (ReferenceSpeed10 > 0) AND (ReferenceSpeed10 <= 100);

IF NOT Valid THEN
    Invalid := TRUE;
ELSE
    // Promote to DINT for safe arithmetic
    LVal      := INT_TO_DINT(LeftSpeed10);
    RVal      := INT_TO_DINT(RightSpeed10);
    RefVal    := INT_TO_DINT(ReferenceSpeed10);

    DiffLR    := LVal - RVal;
    SumLR     := LVal + RVal;
    TargetVal := INT_TO_DINT(13) * RefVal;
    DiffSum   := SumLR - TargetVal;

    IF DiffLR < 0 THEN
        DiffLR := -DiffLR;
    END_IF;
    IF DiffSum < 0 THEN
        DiffSum := -DiffSum;
    END_IF;

    IF (DiffLR <= INT_TO_DINT(1)) AND (DiffSum <= INT_TO_DINT(2)) THEN
        SyncOK := TRUE;
    ELSE
        SyncBad := TRUE;
    END_IF;
END_IF;

END_FUNCTION_BLOCK