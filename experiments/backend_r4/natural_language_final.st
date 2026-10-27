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
    diTmp        : DINT;
END_VAR

(* reset has highest priority *)
IF reset THEN
    diHead := 0;
    diTail := 0;
    diCount := 0;
    elementCount := 0;
    status := 16#0000;
    xEnqueuePrev := enqueue;
    xDequeuePrev := dequeue;
    RETURN;
END_IF

(* bind buffer and item on first invocation *)
IF NOT xBound THEN
    diTmp := PV_COUNT(buffer);
    IF diTmp <= 0 THEN
        xBindFault := TRUE;
        diCapacity := 0;
    ELSIF NOT PV_COMPATIBLE(buffer, item) THEN
        xBindFault := TRUE;
        diCapacity := 0;
    ELSE
        diCapacity := diTmp;
        xBound := TRUE;
    END_IF
END_IF

(* rising edge detection *)
xDoEnqueue := enqueue AND NOT xEnqueuePrev;
xDoDequeue := dequeue AND NOT xDequeuePrev;
xEnqueuePrev := enqueue;
xDequeuePrev := dequeue;

status := 16#0000;

IF xBindFault THEN
    elementCount := 0;
ELSIF xDoEnqueue AND NOT xDoDequeue THEN
    IF diCount >= diCapacity THEN
        status := 16#8002; (* full *)
    ELSE
        PV_WRITE(buffer, diTail, item);
        diTail := diTail + 1;
        IF diTail >= diCapacity THEN
            diTail := 0;
        END_IF
        diCount := diCount + 1;
    END_IF
    elementCount := diCount;
ELSIF xDoDequeue AND NOT xDoEnqueue THEN
    IF diCount <= 0 THEN
        status := 16#8001; (* empty *)
    ELSE
        PV_READ(buffer, diHead, item);
        diHead := diHead + 1;
        IF diHead >= diCapacity THEN
            diHead := 0;
        END_IF
        diCount := diCount - 1;
    END_IF
    elementCount := diCount;
ELSE
    elementCount := diCount;
END_IF

END_FUNCTION_BLOCK
