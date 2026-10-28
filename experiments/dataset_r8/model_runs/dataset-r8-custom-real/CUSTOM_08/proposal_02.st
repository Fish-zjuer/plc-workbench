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
    Valid    : BOOL;
    L        : DINT;
    R        : DINT;
    Ref      : DINT;
    DiffLR   : DINT;
    DiffSum  : DINT;
    SumLR    : DINT;
    Target   : DINT;
END_VAR

// Default: all outputs FALSE, then exactly one TRUE is set below
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
    L      := INT_TO_DINT(LeftSpeed10);
    R      := INT_TO_DINT(RightSpeed10);
    Ref    := INT_TO_DINT(ReferenceSpeed10);

    DiffLR  := L - R;
    SumLR   := L + R;
    Target  := INT_TO_DINT(13) * Ref;
    DiffSum := SumLR - Target;

    IF (DiffLR < 0) THEN
        DiffLR := -DiffLR;
    END_IF;
    IF (DiffSum < 0) THEN
        DiffSum := -DiffSum;
    END_IF;

    IF (DiffLR <= INT_TO_DINT(1)) AND (DiffSum <= INT_TO_DINT(2)) THEN
        SyncOK := TRUE;
    ELSE
        SyncBad := TRUE;
    END_IF;
END_IF;

END_FUNCTION_BLOCK