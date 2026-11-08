FUNCTION_BLOCK FB_SpectrometerQualification

   VAR_INPUT 
      Maintenance : BOOL;   // Maintenance mode.
      CalibDone : BOOL;   // External calibration-complete level.
      MeasureReq : BOOL;   // Measurement request.
   END_VAR 
   VAR_OUTPUT 
      State : USINT;   // 0 waiting for calibration, 1 ready, 2 maintenance.
      CalibReq : BOOL;   // Request the upstream calibration module.
      MaintLamp : BOOL;   // Maintenance indication.
      MeasurePermit : BOOL;   // Ordinary measurement eligibility.
   END_VAR 
   VAR 
      preState : USINT;   // pre-scan state
      newState : USINT;   // updated state
   END_VAR
VAR_INPUT
WBTEMP_0 : USINT;
WBTEMP_1 : USINT;
END_VAR
 

     
preState := WBTEMP_0;
newState := WBTEMP_1;
	// Capture the pre-scan state (output retains the value of the previous call).
	preState := State;

	// At most one transition per call; maintenance has priority.
	IF Maintenance THEN
	    newState := 2;
	ELSIF preState = 2 THEN
	    // Maintenance-exit scan always returns to 0, even if CalibDone = TRUE.
	    newState := 0;
	ELSIF preState = 0 THEN
	    IF CalibDone THEN
	        newState := 1;
	    ELSE
	        newState := 0;
	    END_IF;
	ELSE
	    newState := 1;
	END_IF;

	State := newState;

	// Output mapping uses the updated state.
	CalibReq := (newState = 0);
	MaintLamp := (newState = 2);
	MeasurePermit := MeasureReq AND (newState = 1);

END_FUNCTION_BLOCK