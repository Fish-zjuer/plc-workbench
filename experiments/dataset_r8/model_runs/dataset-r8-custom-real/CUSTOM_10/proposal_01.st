FUNCTION_BLOCK FB_InventoryRequest
VAR_INPUT
    RequestBtn : BOOL;
    ServiceReady : BOOL;
    Busy : BOOL;
    Cancel : BOOL;
END_VAR
VAR_OUTPUT
    Pending : BOOL := FALSE;
    RequestLamp : BOOL := FALSE;
    Dispatched : BOOL := FALSE;
END_VAR
VAR
    PrevCall : BOOL := FALSE;
    rise : BOOL;
    request : BOOL;
    canServe : BOOL;
END_VAR

rise := RequestBtn AND NOT PrevCall;
request := Pending OR rise;
canServe := ServiceReady AND NOT Busy;

IF Cancel THEN
    Pending := FALSE;
    Dispatched := FALSE;
ELSIF request AND canServe THEN
    Pending := FALSE;
    Dispatched := TRUE;
ELSE
    Pending := request;
    Dispatched := FALSE;
END_IF;

RequestLamp := Pending;
PrevCall := RequestBtn;
END_FUNCTION_BLOCK