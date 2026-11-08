FUNCTION_BLOCK Q01
VAR_INPUT
    bottleSensor : BOOL;
    cleaningConfirmButton : BOOL;
    fillingConfirmButton : BOOL;
    cappingConfirmButton : BOOL;
    packingConfirmButton : BOOL;
    finishedButton : BOOL;
END_VAR

VAR_OUTPUT
    Pump_Motor : BOOL;
    Filling_Valve : BOOL;
    Capping_Machine : BOOL;
    Packing_Machine : BOOL;
    Completion_Light : BOOL;
END_VAR

VAR
    state : INT := 0; // 0: Idle, 1: Cleaning, 2: Filling, 3: Capping, 4: Packing, 5: Done
END_VAR

     
    CASE state OF
        0: // Idle State
            // Reset all outputs
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;

            IF bottleSensor THEN
                state := 1; // Transition to Cleaning
            END_IF;

        1: // Cleaning State
            Pump_Motor := TRUE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;

            IF cleaningConfirmButton THEN
                state := 2; // Transition to Filling
            END_IF;

        2: // Filling State
            Pump_Motor := FALSE;
            Filling_Valve := TRUE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;

            IF fillingConfirmButton THEN
                state := 3; // Transition to Capping
            END_IF;

        3: // Capping State
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := TRUE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;

            IF cappingConfirmButton THEN
                state := 4; // Transition to Packing
            END_IF;

        4: // Packing State
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := TRUE;
            Completion_Light := FALSE;

            IF packingConfirmButton THEN
                state := 5; // Transition to Done
            END_IF;

        5: // Done State
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := TRUE;

            IF finishedButton THEN
                state := 0; // Reset to Idle for next cycle
            END_IF;

        ELSE
            // Default case to prevent undefined behavior
            state := 0;
    END_CASE;
END_FUNCTION_BLOCK