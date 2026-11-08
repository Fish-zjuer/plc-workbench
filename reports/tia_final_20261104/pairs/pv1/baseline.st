FUNCTION_BLOCK Demo
VAR_INPUT x : DINT; END_VAR
VAR_OUTPUT y : DINT; END_VAR
VAR_IN_OUT a : VARIANT; b : VARIANT; END_VAR
VAR copyDone : BOOL; idx : DINT; END_VAR
idx := 1; copyDone := PV_WRITE(a, idx, b); idx := 0; copyDone := PV_READ(a, idx, b); idx := 1; copyDone := PV_READ(a, idx, b);
END_FUNCTION_BLOCK