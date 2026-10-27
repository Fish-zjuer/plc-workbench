FUNCTION_BLOCK BlowerControl
VAR_INPUT
    DO_LOW              : BOOL;
    AERATION_E_STOP_NC  : BOOL;
END_VAR
VAR_OUTPUT
    BLOWER_RUN                  : BOOL;
    AERATION_BLOWER_CYCLE_COUNT : UINT;
END_VAR
VAR
    StartDelay : TON;
    PreviousRun : BOOL := FALSE;
END_VAR

(* The timer resets whenever demand is absent or the E-stop is active. *)
StartDelay(IN := DO_LOW AND AERATION_E_STOP_NC, PT := T#5s);

IF NOT DO_LOW OR NOT AERATION_E_STOP_NC THEN
    BLOWER_RUN := FALSE;
ELSE
    BLOWER_RUN := StartDelay.Q;
END_IF;

(* Count only the false-to-true transition of the run command. *)
IF BLOWER_RUN AND NOT PreviousRun THEN
    AERATION_BLOWER_CYCLE_COUNT := AERATION_BLOWER_CYCLE_COUNT + 1;
END_IF;
PreviousRun := BLOWER_RUN;
END_FUNCTION_BLOCK
