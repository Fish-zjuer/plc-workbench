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
    FirstScan : BOOL := TRUE;
    PrevEnable : BOOL := FALSE;
    Origin : LREAL := 0.0;
    Spacing : LREAL := 0.0;
    LastDistance : LREAL := 0.0;
    Crossed : LREAL := 0.0;
    Issued : UDINT := 0;
    Missed : UDINT := 0;
    Err : BOOL := FALSE;
    InitScan : BOOL := FALSE;
    NewK : LREAL := 0.0;
    Delta : LREAL := 0.0;
    AddMissed : UDINT := 0;
  END_VAR

       
    InitScan := FirstScan OR Reset OR (Enable AND NOT PrevEnable);
    IF InitScan THEN
      IF (DistanceMm >= 0.0) AND (SpacingMm > 0.0) THEN
        Origin := DistanceMm;
        Spacing := SpacingMm;
        LastDistance := DistanceMm;
        Crossed := 0.0;
        Issued := 0;
        Missed := 0;
        Err := FALSE;
        CapturePulse := FALSE;
        CaptureCount := 0;
        MissedCount := 0;
        Error := FALSE;
      ELSE
        Err := TRUE;
        CapturePulse := FALSE;
        CaptureCount := Issued;
        MissedCount := Missed;
        Error := TRUE;
      END_IF;
    ELSIF (NOT Enable) OR Err THEN
      CapturePulse := FALSE;
      CaptureCount := Issued;
      MissedCount := Missed;
      Error := Err;
    ELSE
      IF (DistanceMm < 0.0) OR (DistanceMm < LastDistance) THEN
        Err := TRUE;
        CapturePulse := FALSE;
        CaptureCount := Issued;
        MissedCount := Missed;
        Error := TRUE;
      ELSE
        NewK := FLOOR((DistanceMm - Origin) / Spacing);
        Delta := NewK - Crossed;
        IF Delta > 0.0 THEN
          IF CameraBusy THEN
            CapturePulse := FALSE;
            AddMissed := REAL_TO_UDINT(Delta);
          ELSE
            CapturePulse := TRUE;
            Issued := Issued + 1;
            AddMissed := REAL_TO_UDINT(Delta - 1.0);
          END_IF;
          Missed := Missed + AddMissed;
        ELSE
          CapturePulse := FALSE;
        END_IF;
        Crossed := NewK;
        LastDistance := DistanceMm;
        CaptureCount := Issued;
        MissedCount := Missed;
        Error := Err;
      END_IF;
    END_IF;
    PrevEnable := Enable;
    FirstScan := FALSE;
  END_FUNCTION_BLOCK
