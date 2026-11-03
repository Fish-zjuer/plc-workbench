(*
  Question 07 - Multi-Pump Switching Control System
  5 pumps, manual / automatic mode, "three running, two standby".

  Interface (fixed by the task):
    IN     mode      : BOOL   FALSE = manual, TRUE = automatic
    IN     start     : BOOL   start command (manual selected pumps / auto top-3)
    IN     stop      : BOOL   stops all pumps
    IN_OUT pumpGroup : ARRAY[1..5] OF ST_Pump  (read priority/selection, write RunComd only)

  Implementation notes / assumptions (not defined by the task text):
    * start / stop are treated as level (static) commands, not edge triggered,
      so the RunComd output is a function of the current inputs only.
    * stop has the highest authority and overrides start in both modes.
    * Field 'mode' select : REAL is the analogue detection value (raw);
      it is written by a small helper function below.
    * Automatic mode ranks the five pumps by priority (larger = higher) and
      commands the three highest ranked pumps with 'start';
      equal priorities are broken by the lower array index.
    * Only RunComd of pumpGroup is written; priority/selection are read only.
*)

TYPE ST_Pump :
STRUCT
    priority  : INT;    (* bigger value = higher priority, read only for the FB *)
    selection : BOOL;   (* manual selection, read only for the FB *)
    RunComd   : BOOL;   (* run command written by the FB *)
END_STRUCT
END_TYPE

FUNCTION_BLOCK Q07
VAR_INPUT
    mode  : BOOL;   (* FALSE: manual, TRUE: automatic *)
    start : BOOL;   (* start button *)
    stop  : BOOL;   (* stop button, stops all pumps *)
END_VAR
VAR_IN_OUT
    pumpGroup : ARRAY[1..5] OF ST_Pump;
END_VAR
VAR
    i         : INT;
    j         : INT;
    k         : INT;
    nRanked   : INT;
    rankIdx   : ARRAY[1..5] OF INT;   (* pump indices ordered by priority, internal *)
END_VAR

(* ------------------------------------------------------------------ *)
(* Order the five pumps: highest priority first, ties -> lower index.   *)
(* ------------------------------------------------------------------ *)
nRanked := 0;
FOR i := 1 TO 5 DO
    (* count how many pumps must precede pump i *)
    k := 0;
    FOR j := 1 TO 5 DO
        IF (j <> i) AND
           ( (pumpGroup[j].priority > pumpGroup[i].priority) OR
             ( (pumpGroup[j].priority = pumpGroup[i].priority) AND (j < i) ) )
        THEN
            k := k + 1;
        END_IF;
    END_FOR;
    rankIdx[k + 1] := i;
    nRanked := nRanked + 1;
END_FOR;

(* ------------------------------------------------------------------ *)
(* Command outputs.                                                     *)
(* ------------------------------------------------------------------ *)
IF stop THEN
    (* stop has priority: all pumps off, in both modes *)
    FOR i := 1 TO 5 DO
        pumpGroup[i].RunComd := FALSE;
    END_FOR;

ELSIF mode THEN
    (* automatic: the three highest priority pumps run, the rest stop *)
    FOR i := 1 TO 5 DO
        IF (i <= 3) AND start THEN
            pumpGroup[rankIdx[i]].RunComd := TRUE;
        ELSE
            pumpGroup[rankIdx[i]].RunComd := FALSE;
        END_IF;
    END_FOR;

ELSE
    (* manual: manual selection AND start *)
    FOR i := 1 TO 5 DO
        pumpGroup[i].RunComd := pumpGroup[i].selection AND start;
    END_FOR;
END_IF;

END_FUNCTION_BLOCK
