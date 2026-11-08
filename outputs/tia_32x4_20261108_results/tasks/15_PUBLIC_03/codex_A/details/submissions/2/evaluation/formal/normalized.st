FUNCTION_BLOCK Q03

   VAR_INPUT
      Value : REAL;
      hiLevel : REAL;
      loLevel : REAL;
      hystWindow : REAL;
   END_VAR
   VAR_OUTPUT
      hiAlarm : BOOL;
      loAlarm : BOOL;
      error : BOOL;
      status : WORD;
   END_VAR
   VAR
      validCfg : BOOL;
      invalidLimits : BOOL;
      invalidWindow : BOOL;
      hiSet : BOOL;
      hiReset : BOOL;
      loSet : BOOL;
      loReset : BOOL;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
WBTEMP_3 : BOOL;
WBTEMP_4 : BOOL;
WBTEMP_5 : BOOL;
WBTEMP_6 : BOOL;
END_VAR

     
validCfg := WBTEMP_0;
invalidLimits := WBTEMP_1;
invalidWindow := WBTEMP_2;
hiSet := WBTEMP_3;
hiReset := WBTEMP_4;
loSet := WBTEMP_5;
loReset := WBTEMP_6;
   invalidLimits := loLevel >= hiLevel;
   invalidWindow := (NOT invalidLimits) AND (hystWindow >= (hiLevel - loLevel));
   validCfg := (NOT invalidLimits) AND (NOT invalidWindow);

   IF invalidLimits THEN
      error := TRUE;
      status := 16#8001;
      hiAlarm := FALSE;
      loAlarm := FALSE;
   ELSIF invalidWindow THEN
      error := TRUE;
      status := 16#8002;
   ELSE
      error := FALSE;
      status := 16#0000;
      hiSet := Value > hiLevel;
      hiReset := Value < (hiLevel - hystWindow);
      loSet := Value < loLevel;
      loReset := Value > (loLevel + hystWindow);

      IF hiSet THEN
         hiAlarm := TRUE;
      ELSIF hiReset THEN
         hiAlarm := FALSE;
      END_IF;

      IF loSet THEN
         loAlarm := TRUE;
      ELSIF loReset THEN
         loAlarm := FALSE;
      END_IF;
   END_IF;
END_FUNCTION_BLOCK


