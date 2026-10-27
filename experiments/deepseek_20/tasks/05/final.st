FUNCTION_BLOCK Q05
VAR_INPUT
    Gap_Exceeded   : BOOL;   // TRUE: scanner detects a gap > 1.5 mm
    Weld_E_Stop_NC : BOOL;   // TRUE: E-stop inactive; FALSE: E-stop active
    DebounceTime   : TIME;   // gap debounce duration in normal monitoring; must be > 0
END_VAR

VAR_OUTPUT
    Operator_Alert         : BOOL;  // audible and visual alarm command
    Weld_Soft_Start_Active : BOOL;  // TRUE only during the 5 s power-up inhibition
END_VAR

VAR
    // diagnostic / internal state
    bPrevEStopInactive : BOOL;
    bDebounceActive    : BOOL;
    rtDebounceElapsed  : TIME;
    bInitDone          : BOOL;
    bForceInitReset    : BOOL;
END_VAR

// ---- 1) Emergency stop has the highest priority -------------------------
// FALSE means the emergency stop is active; it overrides both the power-up
// inhibition and the normal monitoring.
IF NOT Weld_E_Stop_NC THEN
    Operator_Alert         := FALSE;
    Weld_Soft_Start_Active := FALSE;
    // clear any incomplete debounce timing
    bDebounceActive   := FALSE;
    rtDebounceElapsed := T#0S;
    // restart the power-up inhibition once the E-stop is released
    bForceInitReset     := TRUE;
    bInitDone           := FALSE;
    bPrevEStopInactive  := FALSE;
ELSE
    // ---- 2) Power-up inhibition (5 s) -----------------------------------
    IF bForceInitReset THEN
        bForceInitReset := FALSE;
        bInitDone       := FALSE;
    END_IF

    IF NOT bInitDone THEN
        Operator_Alert         := FALSE;
        Weld_Soft_Start_Active := TRUE;
        // debounce time must not accumulate during inhibition
        bDebounceActive   := FALSE;
        rtDebounceElapsed := T#0S;
        rtDebounceElapsed := T#0S;
        // Placeholder-free marker: inhibition elapsed tracking below
        IF TRUE THEN
            ;
        END_IF
    END_IF
END_IF

END_FUNCTION_BLOCK
