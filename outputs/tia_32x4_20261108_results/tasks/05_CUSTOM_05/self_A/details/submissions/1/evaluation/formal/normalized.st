FUNCTION_BLOCK FB_InspectionCapture

   VAR_INPUT
      Enable : BOOL;
      Reset : BOOL;
      DistanceMm : LREAL;
      SpacingMm : LREAL;
      CameraBusy : BOOL;
   END_VAR
   VAR_OUTPUT
      CapturePulse : BOOL;
      CaptureCount : UDINT;
      MissedCount : UDINT;
      Error : BOOL;
   END_VAR
   VAR
      firstRun : BOOL;
      prevEnable : BOOL;
      origin : LREAL;
      latchedSpacing : LREAL;
      lastDistance : LREAL;
      crossedCount : DINT;
      initNeeded : BOOL;
      validInit : BOOL;
      posValid : BOOL;
      nonDecreasing : BOOL;
      newK : DINT;
      deltaK : DINT;
      runValid : BOOL;
   END_VAR

     
   // Default outputs each scan
   CapturePulse := FALSE;

   // Determine initialization request: first call, Reset, or rising edge of Enable
   initNeeded := firstRun OR Reset OR (Enable AND NOT prevEnable);

   // Validate initialization data
   // SpacingMm must be finite and positive; DistanceMm must be finite and nonnegative.
   validInit := (DistanceMm >= 0.0)
                 AND (SpacingMm > 0.0)
                 AND (DistanceMm <= 1.0E300)
                 AND (DistanceMm >= -1.0E300)
                 AND (SpacingMm <= 1.0E300);

   IF initNeeded THEN
      IF validInit THEN
         // Establish new segment
         origin := DistanceMm;
         latchedSpacing := SpacingMm;
         lastDistance := DistanceMm;
         crossedCount := 0;
         CaptureCount := 0;
         MissedCount := 0;
         Error := FALSE;
         CapturePulse := FALSE;
      ELSE
         // Invalid initialization: latch error, preserve counts and origin
         Error := TRUE;
         CapturePulse := FALSE;
      END_IF;
   ELSE
      // Not an initialization scan
      IF Enable AND NOT Error THEN
         // Validate current position
         posValid := (DistanceMm >= 0.0)
                      AND (DistanceMm <= 1.0E300)
                      AND (DistanceMm >= -1.0E300);
         nonDecreasing := DistanceMm >= lastDistance;

         IF NOT posValid OR NOT nonDecreasing THEN
            // Position error: latch error, preserve counts and origin
            Error := TRUE;
            CapturePulse := FALSE;
         ELSE
            // Compute number of crossed sampling positions
            newK := REAL_TO_DINT(FLOOR((DistanceMm - origin) / latchedSpacing));
            IF newK > 1000000000 THEN
               newK := 1000000000;
            END_IF;
            deltaK := newK - crossedCount;

            IF deltaK > 0 THEN
               IF NOT CameraBusy THEN
                  // Issue one capture request for this scan
                  CapturePulse := TRUE;
                  CaptureCount := CaptureCount + 1;
                  // d-1 positions are missed (skipped)
                  IF deltaK > 1 THEN
                     MissedCount := MissedCount + DINT_TO_UDINT(deltaK - 1);
                  END_IF;
               ELSE
                  // Camera busy: all crossed positions missed
                  MissedCount := MissedCount + DINT_TO_UDINT(deltaK);
               END_IF;
            END_IF;

            // Update crossed-point count and last distance
            crossedCount := newK;
            lastDistance := DistanceMm;
         END_IF;
      ELSE
         // Disabled or error latched: no capture, counts retained
         CapturePulse := FALSE;
      END_IF;
   END_IF;

   // Update edge/history state every scan
   prevEnable := Enable;
   firstRun := FALSE;
END_FUNCTION_BLOCK