FUNCTION_BLOCK FB_SpectrometerQualification

   VAR_INPUT
      Maintenance : BOOL; // Maintenance mode
      CalibDone : BOOL;   // External calibration-complete level
      MeasureReq : BOOL;  // Measurement request
   END_VAR

   VAR_OUTPUT
      State : USINT;      // 0 waiting for calibration, 1 ready, 2 maintenance
      CalibReq : BOOL;    // Request the upstream calibration module
      MaintLamp : BOOL;   // Maintenance indication
      MeasurePermit : BOOL; // Ordinary measurement eligibility
   END_VAR

   VAR
      prevState : USINT;
   END_VAR

   VAR
      lastState : USINT := 0; // Static variable to hold the state from the previous scan cycle
   END_VAR
VAR_INPUT
WBTEMP_0 : USINT;
END_VAR


     
prevState := WBTEMP_0;
   // Initialize outputs based on requirements if this is the very first execution,
   // though the logic below handles transitions correctly for subsequent scans.
   // Requirement: Initially State=0, CalibReq=TRUE, MaintLamp=FALSE, MeasurePermit=FALSE.
   
   // Capture the pre-scan state before any updates
   prevState := lastState;

   // Control Logic:
   // 1. Maintenance has priority -> State 2
   // 2. If not in maintenance:
   //    - If prev state was 2 (exiting maintenance) -> Force State 0 (Waiting for Calibration)
   //      Note: This happens even if CalibDone is TRUE, per requirement.
   //    - If prev state was 0 AND CalibDone is TRUE -> State 1 (Ready)
   //    - Otherwise -> Stay in prev state (0 stays 0 if !CalibDone, 1 stays 1)

   IF Maintenance THEN
       State := 2;
   ELSIF (prevState = 2) THEN
       State := 0;
   ELSIF (prevState = 0 AND CalibDone) THEN
       State := 1;
   ELSE
       State := prevState;
   END_IF;

   // Update outputs based on the NEW State
   CalibReq := (State = 0);
   MaintLamp := (State = 2);
   MeasurePermit := (MeasureReq AND (State = 1));

   // Store current state for next scan
   lastState := State;
END_FUNCTION_BLOCK