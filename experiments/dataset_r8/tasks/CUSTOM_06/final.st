FUNCTION F_IsFinite : BOOL
VAR_INPUT
  X : LREAL;
END_VAR
F_IsFinite := (X = X) AND ((X - X) = 0.0);
END_FUNCTION

FUNCTION_BLOCK FB_CompressorPressure
VAR_INPUT
  Enable : BOOL;
  Reset : BOOL;
  PressureKpa : LREAL;
  AirUseFlow : LREAL;
  Kp : LREAL;
  Ki : LREAL;
  DtSec : LREAL;
END_VAR
VAR_OUTPUT
  CapacityPct : LREAL;
  Integral : LREAL;
  Saturated : BOOL;
  Error : BOOL;
END_VAR
VAR
  valid : BOOL;
  e : LREAL;
  FF : LREAL;
  prevIntegral : LREAL;
  Ic : LREAL;
  Uc : LREAL;
  U : LREAL;
  reject : BOOL;
END_VAR

IF Reset THEN
  Integral := 0.0;
  CapacityPct := 0.0;
  Saturated := FALSE;
  Error := FALSE;
ELSIF NOT Enable THEN
  CapacityPct := 0.0;
  Saturated := FALSE;
  Error := FALSE;
ELSE
  valid := F_IsFinite(PressureKpa)
       AND F_IsFinite(AirUseFlow)
       AND F_IsFinite(Kp)
       AND F_IsFinite(Ki)
       AND F_IsFinite(DtSec)
       AND (PressureKpa >= 0.0) AND (PressureKpa <= 1000.0)
       AND (AirUseFlow >= 0.0) AND (AirUseFlow <= 90.0)
       AND (Kp >= 0.0) AND (Kp <= 1.0)
       AND (Ki >= 0.0) AND (Ki <= 0.1)
       AND (DtSec >= 0.001) AND (DtSec <= 1.0);
  IF NOT valid THEN
    CapacityPct := 0.0;
    Saturated := FALSE;
    Error := TRUE;
  ELSE
    e := 500.0 - PressureKpa;
    FF := 2.0 * AirUseFlow;
    prevIntegral := Integral;
    Ic := prevIntegral + Ki * e * DtSec;
    Uc := FF + Kp * e + Ic;
    reject := ((Uc > 100.0) AND (e > 0.0)) OR ((Uc < 0.0) AND (e < 0.0));
    IF reject THEN
      Integral := prevIntegral;
    ELSE
      Integral := Ic;
    END_IF;
    U := FF + Kp * e + Integral;
    IF U > 100.0 THEN
      CapacityPct := 100.0;
    ELSIF U < 0.0 THEN
      CapacityPct := 0.0;
    ELSE
      CapacityPct := U;
    END_IF;
    Saturated := (U < 0.0) OR (U > 100.0);
    Error := FALSE;
  END_IF;
END_IF;
END_FUNCTION_BLOCK