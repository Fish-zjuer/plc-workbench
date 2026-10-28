FUNCTION IsFiniteLReal : BOOL
VAR_INPUT
  x : LREAL;
END_VAR
IsFiniteLReal := NOT (x <> x) AND (x <= 1.7976931348623157E308) AND (x >= -1.7976931348623157E308);
END_FUNCTION

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
  first : BOOL := TRUE;
  prevEnable : BOOL := FALSE;
  origin : LREAL := 0.0;
  spacing : LREAL := 1.0;
  lastDistance : LREAL := 0.0;
  k : UDINT := 0;
  issued : UDINT := 0;
  missed : UDINT := 0;
  err : BOOL := FALSE;
  init : BOOL;
  posValid : BOOL;
  spValid : BOOL;
  validInit : BOOL;
  ratio : LREAL;
  newK : UDINT;
  d : UDINT;
END_VAR

init := first OR Reset OR (Enable AND NOT prevEnable);

posValid := IsFiniteLReal(DistanceMm) AND (DistanceMm >= 0.0);
spValid := IsFiniteLReal(SpacingMm) AND (SpacingMm > 0.0);
validInit := posValid AND spValid;

CapturePulse := FALSE;

IF init THEN
  IF validInit THEN
    origin := DistanceMm;
    spacing := SpacingMm;
    lastDistance := DistanceMm;
    k := 0;
    issued := 0;
    missed := 0;
    err := FALSE;
  ELSE
    err := TRUE;
  END_IF;
ELSE
  IF (NOT Enable) OR err THEN
    // hold counts and error state
  ELSE
    IF (NOT posValid) OR (DistanceMm < lastDistance) THEN
      err := TRUE;
    ELSE
      ratio := (DistanceMm - origin) / spacing;
      newK := LREAL_TO_UDINT(FLOOR(ratio));
      d := newK - k;
      IF d > 0 THEN
        IF NOT CameraBusy THEN
          CapturePulse := TRUE;
          issued := issued + 1;
          missed := missed + (d - 1);
        ELSE
          missed := missed + d;
        END_IF;
      END_IF;
      k := newK;
      lastDistance := DistanceMm;
    END_IF;
  END_IF;
END_IF;

CaptureCount := issued;
MissedCount := missed;
Error := err;

prevEnable := Enable;
first := FALSE;

END_FUNCTION_BLOCK