(*
    Public bank question 16 - Flexible Processing Control
    5 workstations: 1# loading, 2#..4# processing, 5# output.
    One motor/conveyor moves the product from one workstation to the next.

    Behaviour implemented here (all details not fixed by the task text are
    marked "UNDEFINED in task, chosen as ..."):

    - processSequence[1..processLength] is the active route, read from [1].
      The caller guarantees that the last active entry is station 5.
    - Idle: waits for sensor1 (raw material at 1#) AND a rising edge of
      station1Start to begin a new product.
    - On start: the first active entry is taken as the first target station.
      The conveyor runs in the direction of that target (left if the target
      number is smaller than the current position, right if greater) and is
      switched off as soon as the product reaches the target station's own
      sensor; the conveyor therefore stops after delivery.
    - If the target is an intermediate station (2#..4#), the block waits for
      the completion signal of that station (station2Complete..
      station4Complete, rising edge), then advances to the next active entry.
    - If the target is station 5 (the output station), the product is
      finished: the conveyor stops at sensor5 and the block returns to idle,
      requiring a new station1Start edge for the next product.
    - A route entry equal to the current station is treated as "already
      there" (no conveyor motion).
    - Out-of-range entries (<1 or >5) are ignored for motion: UNDEFINED in
      task, chosen as "no movement; treat it like a processing station without
      a completion signal", i.e. stay put and keep the conveyor off.
    - processLength outside 1..8 is UNDEFINED in task; chosen as "no
      movement" (the block stays idle and starts no route; no error output is
      provided by the interface).
    - conveyorLeft and conveyorRight are never TRUE at the same time.
*)
FUNCTION_BLOCK Q16
VAR_INPUT
    processLength     : USINT;                       (* active length, 1..8 *)
    sensor1           : BOOL;                        (* sensor at 1# *)
    sensor2           : BOOL;                        (* sensor at 2# *)
    sensor3           : BOOL;                        (* sensor at 3# *)
    sensor4           : BOOL;                        (* sensor at 4# *)
    sensor5           : BOOL;                        (* sensor at 5# *)
    station1Start     : BOOL;                        (* start button at 1# *)
    station2Complete  : BOOL;                        (* 2# processing complete *)
    station3Complete  : BOOL;                        (* 3# processing complete *)
    station4Complete  : BOOL;                        (* 4# processing complete *)
    processSequence   : ARRAY[1..8] OF USINT;        (* processing sequence *)
END_VAR
VAR_OUTPUT
    conveyorLeft      : BOOL;                        (* conveyor turns left *)
    conveyorRight     : BOOL;                        (* conveyor turns right *)
END_VAR
VAR
    stepNo            : USINT := 0;                  (* 0 = idle, 1 = run route *)
    idx               : USINT := 1;                  (* active sequence index *)
    target            : USINT := 0;                  (* target station of idx *)
    curPos            : USINT := 1;                  (* physical station number *)
    arrIdx            : USINT := 1;                  (* index used to read the array *)
    arrived           : BOOL;                        (* product detected at target *)
    procDone          : BOOL;                        (* target processing finished *)
    procDoneLatched   : BOOL;                        (* completion of target acknowledged *)
    inRange           : BOOL;                        (* processLength within 1..8 *)
    lastStart         : BOOL;                        (* edge memory of station1Start *)
    comp2Mem          : BOOL;                        (* edge memory of station2Complete *)
    comp3Mem          : BOOL;                        (* edge memory of station3Complete *)
    comp4Mem          : BOOL;                        (* edge memory of station4Complete *)
    compSignal        : BOOL;                        (* completion signal of target *)
    compMem           : BOOL;                        (* edge memory of compSignal *)
    idxLimit          : USINT := 0;                  (* last active index *)
END_VAR

(* ------------------------------------------------------------------ *)
(* range of the caller supplied processLength                          *)
(* ------------------------------------------------------------------ *)
inRange := (processLength >= 1) AND (processLength <= 8);
IF inRange THEN
    idxLimit := processLength;
ELSE
    idxLimit := 0;                                   (* invalid length: no route *)
END_IF;

(* ------------------------------------------------------------------ *)
(* product detection at the current target station                     *)
(* ------------------------------------------------------------------ *)
CASE target OF
    1: arrived := sensor1;
    2: arrived := sensor2;
    3: arrived := sensor3;
    4: arrived := sensor4;
    5: arrived := sensor5;
ELSE
    arrived := FALSE;                                (* no sensor for such an entry *)
END_CASE;

(* ------------------------------------------------------------------ *)
(* completion signal belonging to the current target station           *)
(* ------------------------------------------------------------------ *)
compSignal := FALSE;
IF target = 2 THEN
    compSignal := station2Complete;
ELSIF target = 3 THEN
    compSignal := station3Complete;
ELSIF target = 4 THEN
    compSignal := station4Complete;
END_IF;

comp2Mem := station2Complete;
comp3Mem := station3Complete;
comp4Mem := station4Complete;

(* rising edge of the completion signal of the current target station *)
procDone := compSignal AND NOT compMem;
compMem  := compSignal;

(* ------------------------------------------------------------------ *)
(* route state machine                                                 *)
(* ------------------------------------------------------------------ *)
CASE stepNo OF
0:  (* idle: wait for raw material at 1# and a start edge *)
    conveyorLeft  := FALSE;
    conveyorRight := FALSE;
    curPos   := 1;
    idx      := 1;
    target   := 0;
    IF sensor1 AND station1Start AND NOT lastStart AND (idxLimit >= 1) THEN
        arrIdx := 1;
        target := processSequence[arrIdx];
        stepNo := 1;
    END_IF;

1:  (* moving to, or waiting at, the current target station *)
    IF target > curPos THEN
        conveyorRight := TRUE;
        conveyorLeft  := FALSE;
    ELSIF (target >= 1) AND (target < curPos) THEN
        conveyorLeft  := TRUE;
        conveyorRight := FALSE;
    ELSE
        conveyorLeft  := FALSE;
        conveyorRight := FALSE;
    END_IF;

    (* stop after delivery to the target station *)
    IF arrived THEN
        conveyorLeft  := FALSE;
        conveyorRight := FALSE;
        curPos        := target;
        IF curPos >= 5 THEN
            (* delivered to output station 5#: product finished *)
            stepNo := 0;
        ELSIF (curPos >= 2) AND (curPos <= 4) THEN
            (* 2#..4# processing station: wait for its completion signal *)
            IF procDone THEN
                IF idx >= idxLimit THEN
                    (* sequence exhausted without reaching 5#:
                       caller violated the contract, stop the route *)
                    stepNo := 0;
                ELSE
                    idx    := idx + 1;
                    arrIdx := idx;
                    target := processSequence[arrIdx];
                END_IF;
            END_IF;
        ELSE
            (* invalid entry: no sensor / no completion signal available *)
            stepNo := 1;                             (* stay put, conveyor off *)
        END_IF;
    END_IF;

ELSE
    stepNo := 0;
    conveyorLeft  := FALSE;
    conveyorRight := FALSE;
END_CASE;

lastStart := station1Start;
END_FUNCTION_BLOCK
