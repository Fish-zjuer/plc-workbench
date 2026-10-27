TYPE Q05_INIT_PHASE :
(
    INITIALIZING := 0,
    MONITORING   := 1
);
END_TYPE

FUNCTION_BLOCK Q05
VAR_INPUT
    Gap_Exceeded   : BOOL;   // TRUE: scanner sees gap > 1.5 mm
    Weld_E_Stop_NC : BOOL;   // TRUE: E-stop inactive, FALSE: E-stop active
    DebounceTime   : TIME;   // gap debounce duration in normal monitoring
END_VAR

VAR_OUTPUT
    Operator_Alert       : BOOL;  // audible / visual alarm command
    Weld_Soft_Start_Active : BOOL; // TRUE during the 5 s power-up inhibition
END_VAR

VAR
    fbPowerUpTimer  : TON;              // 5 s power-up inhibition timer
    fbDebounceTimer : TON;              // gap debounce timer
    bEStopActive    : BOOL;             // current E-stop state
    ePhase          : Q05_INIT_PHASE;   // initialisation / monitoring
    bInitDone       : BOOL;             // power-up inhibition finished
END_VAR

// ---- E-stop priority: highest, evaluated first --------------------------
bEStopActive := NOT Weld_E_Stop_NC;

IF bEStopActive THEN
    // E-stop overrides initialisation and normal monitoring.
    Operator_Alert         := FALSE;
    Weld_Soft_Start_Active := FALSE;
    fbDebounceTimer(IN := FALSE, PT := T#0S);
    fbPowerUpTimer(IN := FALSE, PT := T#5S);
    // Force a full new 5 s inhibition period after the E-stop is released.
    bInitDone := FALSE;
    ePhase    := Q05_INITIALIZING;
ELSE
    // ---- Power-up 5 s inhibition ---------------------------------------
    IF NOT bInitDone THEN
        ePhase := Q05_INITIALIZING;
        fbDebounceTimer(IN := FALSE, PT := DebounceTime);
        fbPowerUpTimer(IN := TRUE, PT := T#5S);
        IF fbPowerUpTimer.Q THEN
            bInitDone := TRUE;
            ePhase    := Q05.MONITORING;
        END_IF
    END_IF

    IF ePhase = Q05_INITIALIZING OR NOT bInitDone THEN
        // Inhibition period: no alarm, soft-start active, no debounce timing.
        Operator_Alert         := FALSE;
        Weld_Soft_Start_Active := TRUE;
        fbPowerUpTimer(IN := TRUE, PT := T#5S);
        fbDebounceTimer(IN := FALSE, PT := DebounceTime);
        IF fbPowerUpTimer.Q THEN
            bInitDone := TRUE;
            ePhase    := Q05.MONITORING;
        END_IF
    ELSE
        // ---- Normal monitoring ------------------------------------------
        Weld_Soft_Start_Active := FALSE;
        fbPowerUpTimer(IN := FALSE, PT := T#5S);

        IF NOT Gap_Exceeded THEN
            // Signal dropped: switch off alarm and clear debounce timing.
            Operator_Alert := FALSE;
            fbDebounceTimer(IN := FALSE, PT := DebounceTime);
        ELSE
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
