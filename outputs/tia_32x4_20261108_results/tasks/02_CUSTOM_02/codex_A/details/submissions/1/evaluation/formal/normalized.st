FUNCTION_BLOCK FB_HmiAccess

VAR_INPUT
  SessionValid : BOOL;
  Role : USINT;
  Page : USINT;
  WriteReq : BOOL;
  WriteValue : LREAL;
END_VAR

VAR_OUTPUT
  ViewAllowed : BOOL;
  WriteAllowed : BOOL;
  Accepted : BOOL;
  Denied : BOOL;
  ParamValue : LREAL;
END_VAR

VAR
  PageValid : BOOL;
  PagePermitted : BOOL;
  RoleWriteOk : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
END_VAR


     
PageValid := WBTEMP_0;
PagePermitted := WBTEMP_1;
RoleWriteOk := WBTEMP_2;
  PageValid := (Page >= 1) AND (Page <= 4);
  PagePermitted := FALSE;
  RoleWriteOk := FALSE;

  CASE Role OF
    1:
      PagePermitted := (Page = 1) OR (Page = 2);
    2:
      PagePermitted := (Page = 1) OR (Page = 2) OR (Page = 4);
      RoleWriteOk := TRUE;
    3:
      PagePermitted := PageValid;
      RoleWriteOk := TRUE;
  ELSE
    PagePermitted := FALSE;
    RoleWriteOk := FALSE;
  END_CASE;

  ViewAllowed := SessionValid AND PagePermitted;
  WriteAllowed := SessionValid AND RoleWriteOk AND (Page = 4);

  IF NOT WriteReq THEN
    Accepted := FALSE;
    Denied := FALSE;
  ELSIF WriteAllowed AND (WriteValue >= 0.0) AND (WriteValue <= 100.0) THEN
    ParamValue := WriteValue;
    Accepted := TRUE;
    Denied := FALSE;
  ELSE
    Accepted := FALSE;
    Denied := TRUE;
  END_IF;

END_FUNCTION_BLOCK