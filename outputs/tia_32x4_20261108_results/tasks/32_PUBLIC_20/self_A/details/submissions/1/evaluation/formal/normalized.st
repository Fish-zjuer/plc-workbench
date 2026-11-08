FUNCTION_BLOCK Q20

   VAR_INPUT 
      Mode : BOOL;   // 0 = manual, 1 = automatic
      ForwardButton : BOOL;
      ReverseButton : BOOL;
      SensorFeed : BOOL;
      SensorWash : BOOL;
      SensorWeight : BOOL;
      SensorFiring : BOOL;
      SensorOutput : BOOL;
      washComplete : BOOL;
      weightComplete : BOOL;
      weight : REAL;
      firingComplete : BOOL;
   END_VAR
   VAR_OUTPUT 
      MotorForward : BOOL;
      MotorReverse : BOOL;
      kick : BOOL;
      CompletionLight : BOOL;
      firingTemp : REAL;
   END_VAR
   VAR 
      step : INT;               // 0 idle,1 toWash,2 waitWash,3 toWeight,4 waitWeight,5 toFiring,6 waitFiring,7 toOutput,8 finished
      kickPulse : BOOL;
   END_VAR
   VAR 
      qualified : BOOL;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
END_VAR


     
qualified := WBTEMP_0;

   // ---- default outputs ----
   MotorForward := FALSE;
   MotorReverse := FALSE;
   kick := FALSE;

   qualified := (weight >= 100.0) AND (weight <= 200.0);

   IF NOT Mode THEN
      // ================= MANUAL MODE =================
      step := 0;
      CompletionLight := SensorOutput;
      firingTemp := 0.0;
      IF ForwardButton AND NOT ReverseButton THEN
         MotorForward := TRUE;
         MotorReverse := FALSE;
      ELSIF ReverseButton AND NOT ForwardButton THEN
         MotorReverse := TRUE;
         MotorForward := FALSE;
      ELSE
         MotorForward := FALSE;
         MotorReverse := FALSE;
      END_IF;
   ELSE
      // ================= AUTOMATIC MODE =================
      CASE step OF
         0: // idle, waiting at feed station
            CompletionLight := FALSE;
            IF SensorFeed THEN
               MotorForward := TRUE;
               step := 1;
            END_IF;

         1: // moving to wash
            MotorForward := TRUE;
            IF SensorWash THEN
               MotorForward := FALSE;
               step := 2;
            END_IF;

         2: // waiting wash complete
            IF washComplete THEN
               MotorForward := TRUE;
               step := 3;
            END_IF;

         3: // moving to weight
            MotorForward := TRUE;
            IF SensorWeight THEN
               MotorForward := FALSE;
               step := 4;
            END_IF;

         4: // waiting weight complete
            IF weightComplete THEN
               IF qualified THEN
                  // temperature 100..200 -> 500..550
                  firingTemp := 500.0 + 0.5 * (weight - 100.0);
                  kick := FALSE;
                  MotorForward := TRUE;
                  step := 5;
               ELSE
                  kick := TRUE;
                  firingTemp := 0.0;
                  MotorForward := FALSE;
                  // remain until weight becomes valid again / weightComplete drops
                  IF NOT weightComplete THEN
                     step := 3;
                  END_IF;
               END_IF;
            END_IF;

         5: // moving to firing
            MotorForward := TRUE;
            IF SensorFiring THEN
               MotorForward := FALSE;
               step := 6;
            END_IF;

         6: // waiting firing complete
            IF firingComplete THEN
               MotorForward := TRUE;
               step := 7;
            END_IF;

         7: // moving to output
            MotorForward := TRUE;
            IF SensorOutput THEN
               MotorForward := FALSE;
               CompletionLight := TRUE;
               step := 8;
            END_IF;

         8: // finished product present
            CompletionLight := SensorOutput;
            IF NOT SensorOutput THEN
               // product taken away; ready for next cycle
               step := 0;
            END_IF;

         ELSE
            step := 0;
      END_CASE;
   END_IF;

END_FUNCTION_BLOCK