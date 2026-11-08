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
      statIntegral : LREAL;
   END_VAR
   VAR
      valid : BOOL;
      e : LREAL;
      FF : LREAL;
      Ic : LREAL;
      Uc : LREAL;
      U : LREAL;
      reject : BOOL;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : LREAL;
WBTEMP_2 : LREAL;
WBTEMP_3 : LREAL;
WBTEMP_4 : LREAL;
WBTEMP_5 : LREAL;
WBTEMP_6 : BOOL;
END_VAR


     
valid := WBTEMP_0;
e := WBTEMP_1;
FF := WBTEMP_2;
Ic := WBTEMP_3;
Uc := WBTEMP_4;
U := WBTEMP_5;
reject := WBTEMP_6;
   // Reset has highest priority
   IF Reset THEN
      statIntegral := 0.0;
      Integral := 0.0;
      CapacityPct := 0.0;
      Saturated := FALSE;
      Error := FALSE;
      RETURN;
   END_IF;

   // Disabled: preserve integral, zero output, clear flags
   IF NOT Enable THEN
      Integral := statIntegral;
      CapacityPct := 0.0;
      Saturated := FALSE;
      Error := FALSE;
      RETURN;
   END_IF;

   // Validate inputs
   valid := (PressureKpa >= 0.0) AND (PressureKpa <= 1000.0)
             AND (AirUseFlow >= 0.0) AND (AirUseFlow <= 90.0)
             AND (Kp >= 0.0) AND (Kp <= 1.0)
             AND (Ki >= 0.0) AND (Ki <= 0.1)
             AND (DtSec >= 0.001) AND (DtSec <= 1.0);

   IF NOT valid THEN
      Integral := statIntegral;
      CapacityPct := 0.0;
      Saturated := FALSE;
      Error := TRUE;
      RETURN;
   END_IF;

   // Legal enabled call
   e := 500.0 - PressureKpa;
   FF := 2.0 * AirUseFlow;
   Ic := statIntegral + Ki * e * DtSec;
   Uc := FF + Kp * e + Ic;

   reject := ((Uc > 100.0) AND (e > 0.0)) OR ((Uc < 0.0) AND (e < 0.0));

   IF reject THEN
      statIntegral := statIntegral;
   ELSE
      statIntegral := Ic;
   END_IF;

   Integral := statIntegral;
   U := FF + Kp * e + Integral;

   IF U < 0.0 THEN
      CapacityPct := 0.0;
   ELSIF U > 100.0 THEN
      CapacityPct := 100.0;
   ELSE
      CapacityPct := U;
   END_IF;

   Saturated := (U < 0.0) OR (U > 100.0);
   Error := FALSE;

END_FUNCTION_BLOCK