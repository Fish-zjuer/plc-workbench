(* SYNTHETIC FAULT: count_each_scan -- deliberately incorrect. *)
(* Public question 06. Input sampled at scan start, output observed after scan. *)
FUNCTION_BLOCK BlowerControl
VAR_INPUT
    DO_LOW : BOOL;
    AERATION_E_STOP_NC : BOOL;
END_VAR
VAR_OUTPUT
    BLOWER_RUN : BOOL := FALSE;
    AERATION_BLOWER_CYCLE_COUNT : UINT := 0;
END_VAR
VAR
    startDelay : TON;
    previousRun : BOOL := FALSE;
END_VAR

startDelay(IN := DO_LOW AND AERATION_E_STOP_NC, PT := T#5s);
BLOWER_RUN := DO_LOW AND AERATION_E_STOP_NC AND startDelay.Q;
IF BLOWER_RUN THEN
    AERATION_BLOWER_CYCLE_COUNT := AERATION_BLOWER_CYCLE_COUNT + 1;
END_IF;
previousRun := BLOWER_RUN;
END_FUNCTION_BLOCK
