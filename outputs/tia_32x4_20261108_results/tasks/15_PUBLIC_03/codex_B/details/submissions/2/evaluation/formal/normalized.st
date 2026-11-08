FUNCTION_BLOCK Q03
  VERSION : '0.1'

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

     
    IF loLevel >= hiLevel THEN
        error := TRUE;
        status := 16#8001;
        RETURN;
    ELSIF hystWindow >= (hiLevel - loLevel) THEN
        error := TRUE;
        status := 16#8002;
        RETURN;
    END_IF;

    error := FALSE;
    status := 16#0000;

    IF Value > hiLevel THEN
        hiAlarm := TRUE;
    ELSIF Value < (hiLevel - hystWindow) THEN
        hiAlarm := FALSE;
    END_IF;

    IF Value < loLevel THEN
        loAlarm := TRUE;
    ELSIF Value > (loLevel + hystWindow) THEN
        loAlarm := FALSE;
    END_IF;
END_FUNCTION_BLOCK
