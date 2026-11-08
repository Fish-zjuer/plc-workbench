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
      statFirst : BOOL := TRUE;
      statPrevEnable : BOOL;
      statOrigin : LREAL;
      statSpacing : LREAL;
      statLastDistance : LREAL;
      statK : LREAL;
      statNewK : LREAL;
      statD : LREAL;
      statValidInit : BOOL;
      statInit : BOOL;
      statErr : BOOL;
   END_VAR
     
   statValidInit := (DistanceMm >= 0.0) AND (SpacingMm > 0.0);
   statInit := statFirst OR Reset OR (Enable AND NOT statPrevEnable);

   CapturePulse := FALSE;

   IF statInit AND statValidInit THEN
      statOrigin := DistanceMm;
      statSpacing := SpacingMm;
      statLastDistance := DistanceMm;
      statK := 0.0;
      CaptureCount := 0;
      MissedCount := 0;
      statErr := FALSE;
      CapturePulse := FALSE;
   ELSIF statInit AND NOT statValidInit THEN
      statErr := TRUE;
      CapturePulse := FALSE;
   ELSE
      IF Enable AND NOT statErr THEN
         IF (DistanceMm < statLastDistance) OR (DistanceMm < 0.0) THEN
            statErr := TRUE;
            CapturePulse := FALSE;
         ELSE
            statNewK := FLOOR((DistanceMm - statOrigin) / statSpacing);
            statD := statNewK - statK;
            IF statD > 0.0 THEN
               IF NOT CameraBusy THEN
                  CapturePulse := TRUE;
                  CaptureCount := CaptureCount + 1;
                  MissedCount := MissedCount + REAL_TO_UDINT(statD) - 1;
               ELSE
                  CapturePulse := FALSE;
                  MissedCount := MissedCount + REAL_TO_UDINT(statD);
               END_IF;
               statK := statNewK;
            END_IF;
            statLastDistance := DistanceMm;
         END_IF;
      ELSE
         CapturePulse := FALSE;
      END_IF;
   END_IF;

   Error := statErr;
   statPrevEnable := Enable;
   statFirst := FALSE;
END_FUNCTION_BLOCK
