FUNCTION_BLOCK FB_CraneSpeedCheck

VAR_INPUT
    LeftSpeed10 : INT;   // Left-side speed in 0.1 RPM units.
    RightSpeed10 : INT;  // Right-side speed in 0.1 RPM units.
    ReferenceSpeed10 : INT; // Reference reduction-shaft speed in 0.1 RPM units.
END_VAR

VAR_OUTPUT
    SyncOK : BOOL;   // Both synchronization and gearing constraints hold.
    SyncBad : BOOL;  // Inputs valid but at least one constraint fails.
    Invalid : BOOL;  // Any channel out of range or reference speed zero.
END_VAR

VAR
    bValid : BOOL;
    nLeft : DINT;
    nRight : DINT;
    nRef : DINT;
    diffLR : DINT;
    sumLR : DINT;
    targetSum : DINT;
    errorSum : DINT;
    absDiff : DINT;
    absError : DINT;
    bSyncCond : BOOL;
    bGearCond : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : DINT;
WBTEMP_2 : DINT;
WBTEMP_3 : DINT;
WBTEMP_4 : DINT;
WBTEMP_5 : DINT;
WBTEMP_6 : DINT;
WBTEMP_7 : DINT;
WBTEMP_8 : DINT;
WBTEMP_9 : DINT;
WBTEMP_10 : BOOL;
WBTEMP_11 : BOOL;
END_VAR


     
bValid := WBTEMP_0;
nLeft := WBTEMP_1;
nRight := WBTEMP_2;
nRef := WBTEMP_3;
diffLR := WBTEMP_4;
sumLR := WBTEMP_5;
targetSum := WBTEMP_6;
errorSum := WBTEMP_7;
absDiff := WBTEMP_8;
absError := WBTEMP_9;
bSyncCond := WBTEMP_10;
bGearCond := WBTEMP_11;
    // Initialize outputs to FALSE before evaluation
    SyncOK := FALSE;
    SyncBad := FALSE;
    Invalid := FALSE;

    // Step 1: Validate Input Ranges
    // Requirement: All three values in 0..100 AND ReferenceSpeed10 > 0
    IF (LeftSpeed10 >= 0 AND LeftSpeed10 <= 100)
       AND (RightSpeed10 >= 0 AND RightSpeed10 <= 100)
       AND (ReferenceSpeed10 > 0 AND ReferenceSpeed10 <= 100)
    THEN
        bValid := TRUE;
    ELSE
        bValid := FALSE;
    END_IF;

    IF NOT bValid THEN
        Invalid := TRUE;
    ELSE
        // Convert to DINT to prevent overflow during calculation
        nLeft := INT_TO_DINT(LeftSpeed10);
        nRight := INT_TO_DINT(RightSpeed10);
        nRef := INT_TO_DINT(ReferenceSpeed10);

        // Check Constraint 1: ABS(LeftSpeed10 - RightSpeed10) <= 1
        diffLR := nLeft - nRight;
        absDiff := ABS(diffLR);
        bSyncCond := (absDiff <= 1);

        // Check Constraint 2: ABS(LeftSpeed10 + RightSpeed10 - 13 * ReferenceSpeed10) <= 2
        // Target ratio is 6.5x per side, so sum should be 13x ref.
        sumLR := nLeft + nRight;
        targetSum := 13 * nRef;
        errorSum := sumLR - targetSum;
        absError := ABS(errorSum);
        bGearCond := (absError <= 2);

        // Combine conditions
        IF bSyncCond AND bGearCond THEN
            SyncOK := TRUE;
        ELSE
            SyncBad := TRUE;
        END_IF;
    END_IF;

END_FUNCTION_BLOCK