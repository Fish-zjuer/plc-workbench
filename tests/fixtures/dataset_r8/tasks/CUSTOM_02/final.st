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
  ParamValue : LREAL := 0.0;
END_VAR
VAR
  validSession : BOOL;
  acceptWrite : BOOL;
END_VAR

validSession := SessionValid AND ((Role = 1) OR (Role = 2) OR (Role = 3));

ViewAllowed := FALSE;
IF validSession THEN
  CASE Role OF
    1:
      IF (Page = 1) OR (Page = 2) THEN
        ViewAllowed := TRUE;
      END_IF;
    2:
      IF (Page = 1) OR (Page = 2) OR (Page = 4) THEN
        ViewAllowed := TRUE;
      END_IF;
    3:
      IF (Page = 1) OR (Page = 2) OR (Page = 3) OR (Page = 4) THEN
        ViewAllowed := TRUE;
      END_IF;
  ELSE
    ViewAllowed := FALSE;
  END_CASE;
END_IF;

WriteAllowed := SessionValid AND ((Role = 2) OR (Role = 3)) AND (Page = 4);

acceptWrite := WriteReq AND WriteAllowed AND (WriteValue >= 0.0) AND (WriteValue <= 100.0);

Accepted := acceptWrite;
Denied := WriteReq AND NOT acceptWrite;

IF acceptWrite THEN
  ParamValue := WriteValue;
END_IF;

END_FUNCTION_BLOCK