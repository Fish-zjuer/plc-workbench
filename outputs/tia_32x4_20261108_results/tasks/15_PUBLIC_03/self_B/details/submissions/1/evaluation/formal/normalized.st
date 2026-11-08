FUNCTION_BLOCK Q03

   VAR_INPUT
      Value : REAL; // Input value
      hiLevel : REAL; // High limit alarm value
      loLevel : REAL; // Low limit alarm value
      hystWindow : REAL; // Hysteresis window
   END_VAR

   VAR_OUTPUT
      hiAlarm : BOOL; // High limit alarm
      loAlarm : BOOL; // Low limit alarm
      error : BOOL; // FALSE: No error occurred; TRUE: Error occurred during execution of FB
      status : WORD; // Status code
   END_VAR

   VAR
      invalidLimits : BOOL;
      invalidWindow : BOOL;
      valid : BOOL;
      highSet : BOOL;
      highReset : BOOL;
      lowSet : BOOL;
      lowReset : BOOL;
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


     
invalidLimits := WBTEMP_0;
invalidWindow := WBTEMP_1;
valid := WBTEMP_2;
highSet := WBTEMP_3;
highReset := WBTEMP_4;
lowSet := WBTEMP_5;
lowReset := WBTEMP_6;
    // Check configuration validity
    invalidLimits := (loLevel >= hiLevel);
    
    // Calculate deviation range
    // If invalidLimits is true, we don't strictly care about the window check per spec, but let's compute safely.
    // Spec: If loLevel >= hiLevel, error=true, status=16#8001, exit program.
    IF invalidLimits THEN
        error := TRUE;
        status := W#16#8001;
        RETURN;
    END_IF;
    
    // Check hysteresis window validity
    // hystWindow >= (hiLevel - loLevel)
    invalidWindow := (hystWindow >= (hiLevel - loLevel));
    
    IF invalidWindow THEN
        error := TRUE;
        status := W#16#8002;
        RETURN;
    END_IF;
    
    // Valid configuration
    error := FALSE;
    status := W#16#0000;
    
    // Determine alarm states based on hysteresis
    // High Alarm Logic:
    // Trigger when Value > hiLevel
    // Exit when Value < hiLevel - hystWindow
    // Hold state otherwise
    
    highSet := (Value > hiLevel);
    highReset := (Value < (hiLevel - hystWindow));
    
    IF highSet THEN
        hiAlarm := TRUE;
    ELSIF highReset THEN
        hiAlarm := FALSE;
    END_IF;
    // Else: hold previous state (no assignment needed as hiAlarm is static/output persistent in this scan context relative to logic flow if not set/reset)
    
    // Low Alarm Logic:
    // Trigger when Value < loLevel
    // Exit when Value > loLevel + hystWindow
    // Hold state otherwise
    
    lowSet := (Value < loLevel);
    lowReset := (Value > (loLevel + hystWindow));
    
    IF lowSet THEN
        loAlarm := TRUE;
    ELSIF lowReset THEN
        loAlarm := FALSE;
    END_IF;
    // Else: hold previous state

END_FUNCTION_BLOCK