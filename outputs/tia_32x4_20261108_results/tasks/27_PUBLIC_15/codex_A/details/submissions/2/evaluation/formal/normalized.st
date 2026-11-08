FUNCTION_BLOCK Q15

   VAR_INPUT
      estop : BOOL;
      opeMode : BOOL;
      valveAStart : BOOL;
      valveBStart : BOOL;
      valveCStart : BOOL;
      valveDStart : BOOL;
      mixMotorStart : BOOL;
      autoStart : BOOL;
      processMode : BOOL;
      levelSensor : INT;
      mixMotorComplete : BOOL;
   END_VAR

   VAR_OUTPUT
      valveARun : BOOL;
      valveBRun : BOOL;
      valveCRun : BOOL;
      valveDRun : BOOL;
      mixMotorRun : BOOL;
   END_VAR

   VAR
      prevValveAStart : BOOL;
      prevValveBStart : BOOL;
      prevValveCStart : BOOL;
      prevValveDStart : BOOL;
      prevMixMotorStart : BOOL;
      prevAutoStart : BOOL;
      autoStep : INT;
      manValveA : BOOL;
      manValveB : BOOL;
      manValveC : BOOL;
      manValveD : BOOL;
      manMixMotor : BOOL;
   END_VAR

   VAR
      riseA : BOOL;
      riseB : BOOL;
      riseC : BOOL;
      riseD : BOOL;
      riseM : BOOL;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
WBTEMP_3 : BOOL;
WBTEMP_4 : BOOL;
END_VAR


     
riseA := WBTEMP_0;
riseB := WBTEMP_1;
riseC := WBTEMP_2;
riseD := WBTEMP_3;
riseM := WBTEMP_4;

   riseA := valveAStart AND NOT prevValveAStart;
   riseB := valveBStart AND NOT prevValveBStart;
   riseC := valveCStart AND NOT prevValveCStart;
   riseD := valveDStart AND NOT prevValveDStart;
   riseM := mixMotorStart AND NOT prevMixMotorStart;

   prevValveAStart := valveAStart;
   prevValveBStart := valveBStart;
   prevValveCStart := valveCStart;
   prevValveDStart := valveDStart;
   prevMixMotorStart := mixMotorStart;

   IF NOT estop THEN
      manValveA := FALSE;
      manValveB := FALSE;
      manValveC := FALSE;
      manValveD := FALSE;
      manMixMotor := FALSE;
      autoStep := 0;
      valveARun := FALSE;
      valveBRun := FALSE;
      valveCRun := FALSE;
      valveDRun := FALSE;
      mixMotorRun := FALSE;
      prevAutoStart := autoStart;
   ELSIF NOT opeMode THEN
      autoStep := 0;
      IF riseA THEN
         manValveA := NOT manValveA;
      END_IF;
      IF riseB THEN
         manValveB := NOT manValveB;
      END_IF;
      IF riseC THEN
         manValveC := NOT manValveC;
      END_IF;
      IF riseD THEN
         manValveD := NOT manValveD;
      END_IF;
      IF riseM THEN
         manMixMotor := NOT manMixMotor;
      END_IF;
      valveARun := manValveA;
      valveBRun := manValveB;
      valveCRun := manValveC;
      valveDRun := manValveD;
      mixMotorRun := manMixMotor;
      prevAutoStart := autoStart;
   ELSE
      IF autoStep = 0 THEN
         IF autoStart AND NOT prevAutoStart THEN
            autoStep := 10;
         END_IF;
      ELSIF autoStep = 10 THEN
         IF levelSensor >= 50 THEN
            autoStep := 20;
         END_IF;
      ELSIF autoStep = 20 THEN
         IF levelSensor >= 80 THEN
            IF processMode THEN
               autoStep := 30;
            ELSE
               autoStep := 50;
            END_IF;
         END_IF;
      ELSIF autoStep = 30 THEN
         IF levelSensor >= 100 THEN
            autoStep := 50;
         END_IF;
      ELSIF autoStep = 50 THEN
         IF mixMotorComplete THEN
            autoStep := 60;
         END_IF;
      END_IF;

      prevAutoStart := autoStart;

      valveARun := (autoStep = 10);
      valveBRun := (autoStep = 20);
      valveCRun := (autoStep = 30);
      valveDRun := (autoStep = 60);
      mixMotorRun := (autoStep = 50);
   END_IF;

END_FUNCTION_BLOCK

