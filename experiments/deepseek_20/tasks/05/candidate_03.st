TYPE Q05_PHASE :
(
    Q05_INIT := 0,
    Q05_MONITOR := 1
);
END_TYPE

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
    fbInitTimer     : TON;               // 5 s power-up inhibition timer
    fbDebounceTimer : TON;               // gap debounce timer
    ePhase          : Q05_PHASE;         // INIT / MONITOR
    rtInitElapsed   : TIME;              // explicit elapsed time of the inhibition period
END_VAR

// ---------------------------------------------------------------
// 1) Emergency stop has the highest priority: FALSE means active.
//    It overrides initialisation and normal monitoring.
// ---------------------------------------------------------------
IF NOT Weld_E_Stop_NC THEN
    Operator_Alert         := FALSE;
    Weld_Soft_Start_Active := FALSE;
    // Clear any incomplete timing (debounce and inhibition progress).
    fbDebounceTimer(IN := FALSE, PT := DebounceTime);
    fbInitTimer(IN := FALSE, PT := T#5S);
    rtInitElapsed := T#0S;
    // After the E-stop is released a fresh 5 s inhibition starts.
    ePhase := Q05_INIT;

ELSE
    // -----------------------------------------------------------
    // 2) Power-up inhibition: 5 seconds, debounce time must not accumulate.
    // -----------------------------------------------------------
    IF ePhase = Q05_INIT THEN
        Operator_Alert         := FALSE;
        Weld_Soft_Start_Active := TRUE;
        fbDebounceTimer(IN := FALSE, PT := DebounceTime);  // no accumulation
        fbInitTimer(IN := TRUE, PT := T#5S);
        rtInitElapsed := rtInitElapsed + fbInitTimer.ET - T#0S;
        // Re-evaluate the elapsed inhibition time explicitly, so a single
        // timer-instance update cannot swallow the phase change.
        IF (fbInitTimer.Q) OR (rtInitElapsed >= T#5S) THEN
            ePhase := Q05_MONITOR;
            // Enter monitoring cleanly in this same scan.
            Weld_Soft_Start_Active := FALSE;
        END_IF

    END_IF

    // -----------------------------------------------------------
    // 3) Normal monitoring with debounce (entered once inhibition ended)
    // -----------------------------------------------------------
    IF ePhase = Q05_MONITOR THEN
        fbInitTimer(IN := FALSE, PT := T#5S);
        Weld_Soft_Start_Active := FALSE;

        IF NOT Gap_Exceeded THEN
            // Gap signal FALSE: alarm off, debounce timing cleared.
            Operator_Alert := FALSE;
            fbDebounceTimer(IN := FALSE, PT := DebounceTime);
        ELSE
            // Gap signal TRUE: alarm only after DebounceTime has elapsed.
            fbDebounceTimer(IN := TRUE, PT := DebounceTime);
            IF fbDebounceTimer.Q THEN
                Operator_Alert := TRUE;
            ELSE
                Operator_Alert := FALSE;
            END_IF
        END_IF
    END_IF
END_IF

END_FUNCTION_BLOCK
