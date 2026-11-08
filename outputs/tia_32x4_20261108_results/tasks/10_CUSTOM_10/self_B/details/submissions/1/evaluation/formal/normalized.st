FUNCTION_BLOCK FB_InventoryRequest
VAR_INPUT
    RequestBtn : BOOL; // Inventory-request button; rising-edge registration.
    ServiceReady : BOOL; // Inventory service can receive a task.
    Busy : BOOL; // Inventory resource is busy.
    Cancel : BOOL; // Cancel the pending request; highest priority.
END_VAR

VAR_OUTPUT
    Pending : BOOL; // One pending request.
    RequestLamp : BOOL; // Pending-request indication.
    Dispatched : BOOL; // Task issued in this scan, not work completion.
END_VAR

VAR_IN_OUT
END_VAR

VAR
    PrevCall : BOOL := FALSE; // Static variable to store previous state of RequestBtn for edge detection
END_VAR

VAR
    ButtonRise : BOOL;
    Request : BOOL;
    CanServe : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
END_VAR


     
ButtonRise := WBTEMP_0;
Request := WBTEMP_1;
CanServe := WBTEMP_2;
    // 1. Update internal history and calculate edge detection
    // The requirement states: "Update the previous RequestBtn value every scan, including cancellation scans."
    // We use PrevCall as the static memory for the button's previous state.
    
    // Calculate rising edge: Current button is TRUE AND Previous button was FALSE
    ButtonRise := RequestBtn AND NOT PrevCall;
    
    // Update PrevCall for the next scan immediately after calculating the edge
    PrevCall := RequestBtn;

    // 2. Determine if there is an active request
    // "Let Request=previous_Pending OR current_button_rise."
    // Note: 'previous_Pending' refers to the state of Pending at the start of this scan (before it is updated).
    // In SCL, we read the output variable #Pending directly which holds the value from the last cycle.
    Request := Pending OR ButtonRise;

    // 3. Handle Cancellation (Highest Priority)
    IF Cancel THEN
        Pending := FALSE;
        Dispatched := FALSE;
        // Even though cancelled, we already updated #PrevCall above.
        // RequestLamp will be set to match Pending below.
    ELSE
        // 4. Normal Operation Logic
        // Check if service can accept the task
        CanServe := ServiceReady AND NOT Busy;

        IF Request AND CanServe THEN
            // Dispatch the request
            Dispatched := TRUE;
            Pending := FALSE;
        ELSE
            // No dispatch
            Dispatched := FALSE;
            // Preserve unconsumed request
            // If #Request is true but #CanServe is false, Pending must remain TRUE (or become TRUE if just created)
            // If #Request is false, Pending must be FALSE
            Pending := Request;
        END_IF;
    END_IF;

    // 5. Output Lamp
    // "RequestLamp always equals Pending."
    RequestLamp := Pending;

END_FUNCTION_BLOCK