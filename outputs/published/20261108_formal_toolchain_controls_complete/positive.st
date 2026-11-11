FUNCTION_BLOCK FB_SpectrometerQualification
VAR_INPUT
    Maintenance : BOOL;
    CalibDone : BOOL;
    MeasureReq : BOOL;
END_VAR
VAR_OUTPUT
    State : USINT := 0;
    CalibReq : BOOL := TRUE;
    MaintLamp : BOOL := FALSE;
    MeasurePermit : BOOL := FALSE;
END_VAR
VAR
    preState : USINT;
END_VAR

preState := State;

IF Maintenance THEN
    State := 2;
ELSIF preState = 2 THEN
    State := 0;
ELSIF (preState = 0) AND CalibDone THEN
    State := 1;
ELSE
    State := preState;
END_IF;

CalibReq := (State = 0);
MaintLamp := (State = 2);
MeasurePermit := MeasureReq AND (State = 1);

END_FUNCTION_BLOCK