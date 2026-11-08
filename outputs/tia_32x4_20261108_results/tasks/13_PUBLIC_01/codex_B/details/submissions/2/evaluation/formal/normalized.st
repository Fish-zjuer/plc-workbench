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
    stage : INT := 0;
  END_VAR

     
    // advance only on the confirmation that belongs to the current stage
    IF (stage = 0) AND bottleSensor THEN
        stage := 1;
    ELSIF (stage = 1) AND cleaningConfirmButton THEN
        stage := 2;
    ELSIF (stage = 2) AND fillingConfirmButton THEN
        stage := 3;
    ELSIF (stage = 3) AND cappingConfirmButton THEN
        stage := 4;
    ELSIF (stage = 4) AND packingConfirmButton THEN
        stage := 5;
    ELSIF (stage = 5) AND finishedButton THEN
        stage := 0;
    END_IF;

    CASE stage OF
        0:
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;
        1:
            Pump_Motor := TRUE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;
        2:
            Pump_Motor := FALSE;
            Filling_Valve := TRUE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;
        3:
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := TRUE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;
        4:
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := TRUE;
            Completion_Light := FALSE;
        5:
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := TRUE;
        ELSE
            stage := 0;
            Pump_Motor := FALSE;
            Filling_Valve := FALSE;
            Capping_Machine := FALSE;
            Packing_Machine := FALSE;
            Completion_Light := FALSE;
    END_CASE;
END_FUNCTION_BLOCK
