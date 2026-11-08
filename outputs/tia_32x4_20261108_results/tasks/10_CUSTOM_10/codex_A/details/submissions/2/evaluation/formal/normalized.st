FUNCTION_BLOCK FB_InventoryRequest

VAR_INPUT
   RequestBtn : BOOL;
   ServiceReady : BOOL;
   Busy : BOOL;
   Cancel : BOOL;
END_VAR

VAR_OUTPUT
   Pending : BOOL;
   RequestLamp : BOOL;
   Dispatched : BOOL;
END_VAR

VAR
   PrevCall : BOOL;
END_VAR

VAR
   RiseEdge : BOOL;
   Request : BOOL;
   CanServe : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
END_VAR


     
RiseEdge := WBTEMP_0;
Request := WBTEMP_1;
CanServe := WBTEMP_2;
   RiseEdge := RequestBtn AND NOT PrevCall;
   Request := Pending OR RiseEdge;
   CanServe := ServiceReady AND NOT Busy;

   IF Cancel THEN
      Pending := FALSE;
      Dispatched := FALSE;
   ELSIF Request AND CanServe THEN
      Pending := FALSE;
      Dispatched := TRUE;
   ELSE
      Dispatched := FALSE;
      Pending := Request;
   END_IF;

   RequestLamp := Pending;
   PrevCall := RequestBtn;
END_FUNCTION_BLOCK
