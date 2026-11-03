(*
  Public bank question 18: FIFO First-In-First-Out Queue
  CODESYS Structured Text, target block name: Q18

  Interface kept exactly as specified in question.md:
    IN     enqueue      : BOOL
    IN     dequeue      : BOOL
    IN     reset        : BOOL
    OUT    elementCount : DINT
    OUT    status       : WORD
    IN_OUT item         : VARIANT
    IN_OUT buffer       : VARIANT

  Buffer binding is done from the caller with __VARINFO on both the
  VARIANT and the referenced array; capacity = actual array length.
*)

TYPE Q18_Status :
(
    Q18_NO_ERROR        := 16#0000,
    Q18_ERR_QUEUE_EMPTY := 16#8001,
    Q18_ERR_QUEUE_FULL  := 16#8002
);
END_TYPE


FUNCTION_BLOCK Q18
VAR_INPUT
    enqueue : BOOL;         (* rising edge = one enqueue request *)
    dequeue : BOOL;         (* rising edge = one dequeue request *)
    reset   : BOOL;         (* TRUE resets the queue, highest priority *)
END_VAR
VAR_OUTPUT
    elementCount : DINT;    (* number of valid elements, 0 .. capacity *)
    status       : WORD;    (* 16#0000 / 16#8001 / 16#8002 *)
END_VAR
VAR_IN_OUT
    item   : VARIANT;       (* writable scalar, same type as buffer element *)
    buffer : VARIANT;       (* nonempty 1-D homogeneous array, fixed binding *)
END_VAR
VAR
    (* edge detection memory *)
    xEnqueuePrev : BOOL := FALSE;
    xDequeuePrev : BOOL := FALSE;

    (* queue state, internal only (not exposed as interface) *)
    xBound       : BOOL := FALSE;    (* buffer already validated/bound *)
    xBindFault   : BOOL := FALSE;    (* buffer binding was invalid *)
    diCapacity   : DINT := 0;        (* actual array length of buffer *)
    diHead       : DINT := 0;        (* index of the front element *)
    diTail       : DINT := 0;        (* index where the next element goes *)
    diCount      : DINT := 0;        (* number of valid elements *)

    (* work variables *)
    xResetDone   : BOOL;
    xDoEnqueue   : BOOL;
    xDoDequeue   : BOOL;
    xOk          : BOOL;
    xFull        : BOOL;
    xEmpty       : BOOL;
    diBytes      : DINT;             (* element size in bytes *)
    diLower      : DINT;             (* lower bound of the array *)
    diUpper      : DINT;             (* upper bound of the array *)
    diLen        : DINT;             (* array length, DINT safe *)
    pArray       : POINTER TO BYTE;  (* first element of the bound array *)
    pItem        : POINTER TO BYTE;  (* element behind the item reference *)
    pFrom        : POINTER TO BYTE;
    pTo          : POINTER TO BYTE;
    i            : DINT;
    dwVariantType : DWORD;
    dwItemType    : DWORD;
END_VAR


(* ------------------------------------------------------------------ *)
(* buffer binding: validate once per instance, keep it fixed          *)
(* ------------------------------------------------------------------ *)
IF NOT xBound AND NOT xBindFault THEN
    xBound := TRUE;
    diCapacity := 0;
    IF __ISVALIDREF(buffer) THEN
        dwVariantType := __VARINFO(buffer).TypeClass;
        (* must be a one-dimensional array *)
        IF (dwVariantType AND 16#0000FFFF) = 16#000F THEN
            xOk := __VARINFO(buffer).UpperBound > __VARINFO(buffer).LowerBound;
            IF xOk THEN
                diLower := __VARINFO(buffer).LowerBound;
                diUpper := __VARINFO(buffer).UpperBound;
                diLen   := diUpper - diLower + 1;
                diBytes := __VARINFO(buffer).ElementSize;
                pArray  := __VARINFO(buffer).pData;
                IF (diLen > 0) AND (diBytes > 0) AND (pArray <> 0) THEN
                    diCapacity := diLen;
                    diHead := 0;
                    diTail := 0;
                    diCount := 0;
                    xBindFault := FALSE;
                ELSE
                    xBindFault := TRUE;
                END_IF
            ELSE
                xBindFault := TRUE;
            END_IF
        ELSE
            xBindFault := TRUE;
        END_IF
    ELSE
        (* no buffer associated yet: stay unbound, retry on later calls *)
        xBound := FALSE;
    END_IF
END_IF

(* ------------------------------------------------------------------ *)
(* reset has the highest priority                                     *)
(* ------------------------------------------------------------------ *)
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

(* ------------------------------------------------------------------ *)
(* edge detection                                                     *)
(* ------------------------------------------------------------------ *)
xDoEnqueue := enqueue AND NOT xEnqueuePrev;
xDoDequeue := dequeue AND NOT xDequeuePrev;
xEnqueuePrev := enqueue;
xDequeuePrev := dequeue;

status := Q18_NO_ERROR;

(* ------------------------------------------------------------------ *)
(* item must be a writable scalar of the buffer element type          *)
(* ------------------------------------------------------------------ *)
xOk := __ISVALIDREF(item) AND (diCapacity > 0);
IF xOk THEN
    dwItemType := __VARINFO(item).TypeClass;
    xOk := ((dwItemType AND 16#0000FFFF) = 16#000D)     (* scalar *)
           AND (__VARINFO(item).ElementSize = diBytes)
           AND (__VARINFO(item).pData <> 0);
END_IF

IF xOk THEN
    pArray := __VARINFO(buffer).pData;
    pItem  := __VARINFO(item).pData;
    xFull  := (diCount >= diCapacity);
    xEmpty := (diCount <= 0);

    IF xDoEnqueue AND NOT xDoDequeue THEN
        IF xFull THEN
            (* rejected: no state change, item unchanged *)
            status := Q18_ERR_QUEUE_FULL;
        ELSE
            pTo := pArray + (diTail * diBytes);
            FOR i := 1 TO diBytes DO
                pTo^ := pItem^;
                pTo := pTo + 1;
                pItem := pItem + 1;
            END_FOR
            diTail := diTail + 1;
            IF diTail >= diCapacity THEN
                diTail := 0;
            END_IF
            diCount := diCount + 1;
            status := Q18_NO_ERROR;
        END_IF

    ELSIF xDoDequeue AND NOT xDoEnqueue THEN
        IF xEmpty THEN
            (* rejected: no state change, item unchanged *)
            status := Q18_ERR_QUEUE_EMPTY;
        ELSE
            pFrom := pArray + (diHead * diBytes);
            pItem := __VARINFO(item).pData;
            FOR i := 1 TO diBytes DO
                pItem^ := pFrom^;
                pItem := pItem + 1;
                pFrom := pFrom + 1;
            END_FOR
            diHead := diHead + 1;
            IF diHead >= diCapacity THEN
                diHead := 0;
            END_IF
            diCount := diCount - 1;
            status := Q18_NO_ERROR;
        END_IF
    END_IF
END_IF

elementCount := diCount;
