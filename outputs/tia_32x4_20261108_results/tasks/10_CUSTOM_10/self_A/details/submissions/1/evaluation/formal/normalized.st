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
      ButtonRise : BOOL;
      Request : BOOL;
      CanServe : BOOL;
   END_VAR

        
      // Rising edge of the request button against previous scan value
      ButtonRise := RequestBtn AND NOT PrevCall;

      // Request = previous pending OR new rising edge
      Request := Pending OR ButtonRise;

      // Service can accept a task only when ready and not busy
      CanServe := ServiceReady AND NOT Busy;

      // Cancel has highest priority; otherwise dispatch when service is available
      IF Cancel THEN
         Pending := FALSE;
         Dispatched := FALSE;
      ELSIF Request AND CanServe THEN
         Pending := FALSE;
         Dispatched := TRUE;
      ELSE
         Pending := Request;
         Dispatched := FALSE;
      END_IF;

      // Request lamp always mirrors pending state
      RequestLamp := Pending;

      // Update button history every scan, including cancellation scans
      PrevCall := RequestBtn;
   END_FUNCTION_BLOCK