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
        rise : BOOL;
        request : BOOL;
        canServe : BOOL;
    END_VAR

     
    // Rising edge of the request button (held button must not re-register).
    rise := RequestBtn AND NOT PrevCall;

    // A request is either already latched or newly registered this scan.
    request := Pending OR rise;

    // The service can take a task only when ready and not busy.
    canServe := ServiceReady AND NOT Busy;

    // Cancellation has highest priority: drop everything, keep button history.
    IF Cancel THEN
        Pending := FALSE;
        Dispatched := FALSE;
    ELSIF request AND canServe THEN
        // Issue exactly one task on this scan and consume the request.
        Pending := FALSE;
        Dispatched := TRUE;
    ELSE
        // Busy or not ready: retain the unconsumed request, never claim dispatch.
        Pending := request;
        Dispatched := FALSE;
    END_IF;

    // Update button history every scan, including cancellation scans.
    PrevCall := RequestBtn;

    // Terminal indication mirrors the pending state.
    RequestLamp := Pending;
END_FUNCTION_BLOCK