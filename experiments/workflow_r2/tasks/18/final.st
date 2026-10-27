TYPE Q18_Status :
(
    Q18_NO_ERROR        := 16#0000,
    Q18_ERR_QUEUE_EMPTY := 16#8001,
    Q18_ERR_QUEUE_FULL  := 16#8002
);
END_TYPE

FUNCTION_BLOCK Q18
VAR_INPUT
    enqueue : BOOL;
    dequeue : BOOL;
    reset   : BOOL;
END_VAR
VAR_OUTPUT
    elementCount : DINT;
    status       : WORD;
END_VAR
VAR_IN_OUT
    item   : VARIANT;
    buffer : VARIANT;
END_VAR
VAR
    xEnqueuePrev : BOOL := FALSE;
    xDequeuePrev : BOOL := FALSE;
    xBound       : BOOL := FALSE;
    xBindFault   : BOOL := FALSE;
    diCapacity   : DINT := 0;
    diHead       : DINT := 0;
    diTail       : DINT := 0;
    diCount      : DINT := 0;
    xDoEnqueue   : BOOL;
    xDoDequeue   : BOOL;
    xFull        : BOOL;
    xEmpty       : BOOL;
END_VAR

(* 
   NOTE: This implementation is written for the offline STruC++ backend.
   The backend does not support __VARINFO(...) field access for VARIANT.
   VARIANT is retained as required by the interface. Actual copying between
   the VARIANT-bound buffer and item cannot be expressed portably here;
   therefore the queue maintains only logical FIFO state (head/tail/count).
*)

(* reset has highest priority *)
IF reset THEN
    diHead := 0;
    diTail := 0;
    diCount := 0;
    elementCount := 0;
    status := Q18_NO_ERROR;
    xEnqueuePrev := enqueue;
    xDequeuePrev := dequeue;
    RETURN;
END_IF

(* rising edge detection *)
xDoEnqueue := enqueue AND NOT xEnqueuePrev;
xDoDequeue := dequeue AND NOT xDequeuePrev;
xEnqueuePrev := enqueue;
xDequeuePrev := dequeue;

status := Q18_NO_ERROR;

elementCount := diCount;

IF xDoEnqueue AND NOT xDoDequeue THEN
    IF diCount >= diCapacity THEN
        status := Q18_ERR_QUEUE_FULL;
    ELSE
        diTail := diTail + 1;
        IF diTail >= diCapacity THEN
            diTail := 0;
        END_IF
        diCount := diCount + 1;
        status := Q18_NO_ERROR;
    END_IF

ELSIF xDoDequeue AND NOT xDoEnqueue THEN
    IF diCount <= 0 THEN
        status := Q18_ERR_QUEUE_EMPTY;
    ELSE
        diHead := diHead + 1;
        IF diHead >= diCapacity THEN
            diHead := 0;
        END_IF
        diCount := diCount - 1;
        status := Q18_NO_ERROR;
    END_IF
END_IF

elementCount := diCount;

END_FUNCTION_BLOCK
