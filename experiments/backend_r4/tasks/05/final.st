FUNCTION_BLOCK Q05
VAR_INPUT
    Gap_Exceeded   : BOOL;
    Weld_E_Stop_NC : BOOL;
    DebounceTime   : TIME;
END_VAR

VAR_OUTPUT
    Operator_Alert         : BOOL;
    Weld_Soft_Start_Active : BOOL;
END_VAR

VAR
    fbInitTimer     : TON;
    fbDebounceTimer : TON;
    bInitDone       : BOOL;
    bDebounceActive : BOOL;
END_VAR

// Emergency stop has highest priority.
// It clears the alarm and any incomplete debounce timing immediately.
// It does not restart or cancel the power-up initialization state; once
// initialization has completed it remains completed after an E-stop cycle.
IF NOT Weld_E_Stop_NC THEN
    Operator_Alert         := FALSE;
    Weld_Soft_Start_Active := FALSE;
    fbDebounceTimer(IN := FALSE, PT := DebounceTime);
    bDebounceActive := FALSE;
ELSE
    // Power-up inhibition: run only until initialization has completed.
    fbInitTimer(IN := NOT bInitDone, PT := T#5S);
    IF fbInitTimer.Q THEN
        bInitDone := TRUE;
    END_IF

    IF NOT bInitDone THEN
        // 5-second power-up inhibition: no alarm, no debounce accumulation.
        Operator_Alert         := FALSE;
        Weld_Soft_Start_Active := TRUE;
        fbDebounceTimer(IN := FALSE, PT := DebounceTime);
        bDebounceActive := FALSE;
    ELSE
        Weld_Soft_Start_Active := FALSE;

        // Normal gap monitoring with debounce.
        IF Gap_Exceeded THEN
            bDebounceActive := TRUE;
            fbDebounceTimer(IN := TRUE, PT := DebounceTime);
            IF fbDebounceTimer.Q THEN
                Operator_Alert := TRUE;
            END_IF
        ELSE
            Operator_Alert  := FALSE;
            fbDebounceTimer(IN := FALSE, PT := DebounceTime);
            bDebounceActive := FALSE;
        END_IF
    END_IF
END_IF

END_FUNCTION_BLOCK
