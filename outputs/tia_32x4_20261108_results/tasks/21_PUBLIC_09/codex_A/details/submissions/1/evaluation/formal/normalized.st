FUNCTION_BLOCK MovingAverage

   VAR_INPUT 
      cyclicExecution : BOOL;
      trigger : BOOL;
      value : LREAL;
      windowSize : INT;
      reset : BOOL;
   END_VAR 
   VAR_OUTPUT 
      average : LREAL;
      windowSizeReached : BOOL;
      error : BOOL;
      status : WORD;
   END_VAR 
   VAR 
      i : INT;
      buffer : ARRAY[0 .. 99] OF LREAL;
      wrIndex : INT;
      cnt : INT;
      prevTrigger : BOOL;
   END_VAR 
     
   status := 16#0000;
   error := FALSE;

   IF windowSize < 1 OR windowSize > 100 THEN
      error := TRUE;
      status := 16#8200;
      windowSizeReached := FALSE;
      prevTrigger := trigger;
      RETURN;
   END_IF;

   IF cnt > windowSize THEN
      cnt := windowSize;
      IF wrIndex > windowSize THEN
         wrIndex := 0;
      END_IF;
   END_IF;

   IF reset THEN
      cnt := 0;
      wrIndex := 0;
      average := 0.0;
      windowSizeReached := FALSE;
   ELSE
      IF cyclicExecution OR (trigger AND NOT prevTrigger) THEN
         IF cnt < windowSize THEN
            cnt := cnt + 1;
         END_IF;
         IF wrIndex >= cnt THEN
            wrIndex := 0;
         END_IF;
         buffer[wrIndex] := value;
         IF wrIndex >= windowSize - 1 THEN
            wrIndex := 0;
         ELSE
            wrIndex := wrIndex + 1;
         END_IF;
      END_IF;

      IF cnt > 0 THEN
         average := 0.0;
         FOR i := 0 TO cnt - 1 DO
            average := average + buffer[i];
         END_FOR;
         average := average / DINT_TO_LREAL(cnt);
         windowSizeReached := (cnt >= windowSize);
      ELSE
         windowSizeReached := FALSE;
      END_IF;
   END_IF;

   prevTrigger := trigger;
END_FUNCTION_BLOCK
