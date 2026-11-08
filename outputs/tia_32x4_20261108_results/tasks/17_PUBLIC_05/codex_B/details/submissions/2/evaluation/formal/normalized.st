FUNCTION_BLOCK Q05 VERSION : 0.1

VAR_INPUT
    Gap_Exceeded : BOOL;
    Weld_E_Stop_NC : BOOL;
    DebounceTime : TIME := T#1S;
END_VAR

VAR_OUTPUT
    Operator_Alert : BOOL;
    Weld_Soft_Start_Active : BOOL;
END_VAR

VAR
    InitTimer : TON;
    GapTimer : TON;
    InitializationTime : TIME := T#5S;
    EffDebounceTime : TIME;
END_VAR

     
    IF Weld_E_Stop_NC AND InitTimer.Q THEN
        EffDebounceTime := DebounceTime;
    ELSE
        EffDebounceTime := T#0MS;
    END_IF;

    IF NOT Weld_E_Stop_NC THEN
        GapTimer(IN := FALSE, PT := EffDebounceTime);
    ELSIF InitTimer.Q THEN
        GapTimer(IN := Gap_Exceeded, PT := EffDebounceTime);
    ELSE
        GapTimer(IN := FALSE, PT := EffDebounceTime);
    END_IF;

    InitTimer(IN := TRUE, PT := InitializationTime);

    Weld_Soft_Start_Active := NOT InitTimer.Q;
    Operator_Alert := InitTimer.Q AND Weld_E_Stop_NC AND GapTimer.Q;
END_FUNCTION_BLOCK
