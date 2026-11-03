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
    xWriteOk     : BOOL;
    xReadOk      : BOOL;
END_VAR

(* reset has highest priority *)
IF reset THEN
    diHead := 0;
    diTail := 0;
    diCount := 0;
    elementCount := 0;
    status := 0;
    xEnqueuePrev := enqueue;
    xDequeuePrev := dequeue;
    RETURN;
END_IF

(* Bind buffer capacity and check item/buffer element compatibility once. *)
IF NOT xBound THEN
    diCapacity := PV_COUNT(buffer);
    xBindFault := NOT PV_COMPATIBLE(buffer, item);
    xBound := TRUE;
END_IF

(* Rising-edge detection for one operation per request edge. *)
xDoEnqueue := enqueue AND NOT xEnqueuePrev;
xDoDequeue := dequeue AND NOT xDequeuePrev;
xEnqueuePrev := enqueue;
xDequeuePrev := dequeue;

status := 0;

IF xDoEnqueue AND NOT xDoDequeue THEN
    IF xBindFault OR (diCapacity <= 0) OR (diCount >= diCapacity) THEN
        status := 16#8002;
    ELSE
        xWriteOk := PV_WRITE(buffer, diTail, item);
        IF xWriteOk THEN
            diTail := diTail + 1;
            IF diTail >= diCapacity THEN
                diTail := 0;
            END_IF
            diCount := diCount + 1;
        END_IF
    END_IF

ELSIF xDoDequeue AND NOT xDoEnqueue THEN
    IF xBindFault OR (diCapacity <= 0) OR (diCount <= 0) THEN
        status := 16#8001;
    ELSE
        xReadOk := PV_READ(buffer, diHead, item);
        IF xReadOk THEN
            diHead := diHead + 1;
            IF diHead >= diCapacity THEN
                diHead := 0;
            END_IF
            diCount := diCount - 1;
        END_IF
    END_IF
END_IF

elementCount := diCount;

END_FUNCTION_BLOCK
