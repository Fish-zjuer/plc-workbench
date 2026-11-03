FUNCTION_BLOCK FB_RollGeometry
VAR_INPUT
  Reset : BOOL;
  InitialD : LREAL;
  Receiving : BOOL;
  EncoderDelta : DINT;
  SpeedMpm : LREAL;
END_VAR
VAR_OUTPUT
  StoredLength : LREAL := 0.0;
  Diameter : LREAL := 76.0;
  MotorRPM : LREAL := 0.0;
  LimitHit : BOOL := FALSE;
  Error : BOOL := FALSE;
END_VAR
VAR
  initialized : BOOL := FALSE;
  init : BOOL;
  valid : BOOL;
  raw : LREAL;
  deltaL : LREAL;
  lmax : LREAL;
  PI : LREAL := 3.141592653589793;
  CoreD : LREAL := 76.0;
  MaxD : LREAL := 140.0;
  Thk : LREAL := 0.135;
END_VAR

init := (NOT initialized) OR Reset;

valid := (SpeedMpm >= -15.0) AND (SpeedMpm <= 15.0)
     AND (EncoderDelta >= 0) AND (EncoderDelta <= 1000000);
IF init THEN
  valid := valid AND (InitialD >= 76.0) AND (InitialD <= 140.0);
END_IF;

lmax := PI * (MaxD * MaxD - CoreD * CoreD) / (4.0 * Thk);

IF NOT valid THEN
  Error := TRUE;
  MotorRPM := 0.0;
  LimitHit := FALSE;
ELSIF init THEN
  StoredLength := PI * (InitialD * InitialD - CoreD * CoreD) / (4.0 * Thk);
  Diameter := InitialD;
  MotorRPM := 0.0;
  LimitHit := FALSE;
  initialized := TRUE;
  Error := FALSE;
ELSE
  deltaL := DINT_TO_LREAL(EncoderDelta) * PI * 50.0 / 1024.0;
  IF Receiving THEN
    raw := StoredLength + deltaL;
  ELSE
    raw := StoredLength - deltaL;
  END_IF;

  IF raw < 0.0 THEN
    StoredLength := 0.0;
    LimitHit := TRUE;
  ELSIF raw > lmax THEN
    StoredLength := lmax;
    LimitHit := TRUE;
  ELSE
    StoredLength := raw;
    LimitHit := FALSE;
  END_IF;

  Diameter := SQRT(CoreD * CoreD + 4.0 * Thk * StoredLength / PI);

  MotorRPM := SpeedMpm * 1000.0 * 50.0 / (PI * Diameter);
  IF MotorRPM > 6000.0 THEN
    MotorRPM := 6000.0;
  ELSIF MotorRPM < -6000.0 THEN
    MotorRPM := -6000.0;
  END_IF;

  Error := FALSE;
END_IF;

END_FUNCTION_BLOCK