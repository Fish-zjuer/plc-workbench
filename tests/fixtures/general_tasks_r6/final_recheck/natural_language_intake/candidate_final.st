FUNCTION_BLOCK FanHysteresis
VAR_INPUT
    enabled : BOOL;
    temperature : REAL;
END_VAR
VAR_OUTPUT
    fan : BOOL := FALSE;
END_VAR
VAR CONSTANT
    TEMP_ON : REAL := 30.0;
    TEMP_OFF : REAL := 25.0;
END_VAR

IF NOT enabled THEN
    fan := FALSE;
ELSE
    IF temperature >= TEMP_ON THEN
        fan := TRUE;
    ELSIF temperature <= TEMP_OFF THEN
        fan := FALSE;
    END_IF;
END_IF;
END_FUNCTION_BLOCK