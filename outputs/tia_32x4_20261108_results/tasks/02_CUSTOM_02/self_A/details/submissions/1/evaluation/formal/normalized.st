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
      StatParamValue : LREAL;
   END_VAR
   VAR
      RoleValid : BOOL;
      ViewOk : BOOL;
      WriteOk : BOOL;
      AcceptOk : BOOL;
      RangeOk : BOOL;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
WBTEMP_3 : BOOL;
WBTEMP_4 : BOOL;
END_VAR


     
RoleValid := WBTEMP_0;
ViewOk := WBTEMP_1;
WriteOk := WBTEMP_2;
AcceptOk := WBTEMP_3;
RangeOk := WBTEMP_4;

   // Role validity: 1 user, 2 operator, 3 administrator
   RoleValid := (Role = 1) OR (Role = 2) OR (Role = 3);

   // View permission per page and role (valid session required)
   ViewOk := FALSE;
   IF SessionValid AND RoleValid THEN
      CASE Role OF
         1:  // user: pages 1,2
            IF (Page = 1) OR (Page = 2) THEN
               ViewOk := TRUE;
            END_IF;
         2:  // operator: pages 1,2,4
            IF (Page = 1) OR (Page = 2) OR (Page = 4) THEN
               ViewOk := TRUE;
            END_IF;
         3:  // administrator: pages 1..4
            IF (Page = 1) OR (Page = 2) OR (Page = 3) OR (Page = 4) THEN
               ViewOk := TRUE;
            END_IF;
         ELSE
            ViewOk := FALSE;
      END_CASE;
   END_IF;

   // Write permission: valid session, role 2 or 3, page 4
   WriteOk := SessionValid AND ((Role = 2) OR (Role = 3)) AND (Page = 4);

   // Range check on requested value
   RangeOk := (WriteValue >= 0.0) AND (WriteValue <= 100.0);

   // Acceptance evaluation
   AcceptOk := WriteReq AND WriteOk AND RangeOk;

   // Result flags describe the current scan and are not latched
   IF WriteReq THEN
      IF AcceptOk THEN
         Accepted := TRUE;
         Denied := FALSE;
         StatParamValue := WriteValue;
      ELSE
         Accepted := FALSE;
         Denied := TRUE;
      END_IF;
   ELSE
      Accepted := FALSE;
      Denied := FALSE;
   END_IF;

   // Publish outputs
   ViewAllowed := ViewOk;
   WriteAllowed := WriteOk;
   ParamValue := StatParamValue;

END_FUNCTION_BLOCK