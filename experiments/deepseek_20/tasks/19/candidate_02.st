(*
    Q19  Mechanical Arm Control
    Interface unchanged: names, types and directions from the task prompt.
    No ARRAY[*] or VARIANT parameters are used because the task defines none.
*)

TYPE Q19_STATE :
(
    ST_IDLE := 0,
    ST_DOWN1,
    ST_GRIP,
    ST_UP1,
    ST_RIGHT,
    ST_DOWN2,
    ST_RELEASE,
    ST_UP2,
    ST_LEFT,
    ST_DONE
);
END_TYPE

FUNCTION_BLOCK Q19
VAR_INPUT
    ManualMode          : BOOL;
    SingleStepMode      : BOOL;
    SingleCycleMode     : BOOL;
    ContinuousMode      : BOOL;
    EmergencyStop       : BOOL;   (* FALSE = emergency stop active, TRUE = no stop *)
    Start               : BOOL;
    DownButton          : BOOL;
    UpButton            : BOOL;
    LeftButton          : BOOL;
    RightButton         : BOOL;
    GripButton          : BOOL;
    ReleaseButton       : BOOL;
    DownLimitSwitch     : BOOL;
    UpLimitSwitch       : BOOL;
    LeftLimitSwitch     : BOOL;
    RightLimitSwitch    : BOOL;
    GripLimitSwitch     : BOOL;
    ReleaseLimitSwitch  : BOOL;
END_VAR
VAR_OUTPUT
    MoveDown            : BOOL;
    MoveUp              : BOOL;
    MoveLeft            : BOOL;
    MoveRight           : BOOL;
    ActivateGrip        : BOOL;
    ActivateRelease     : BOOL;
END_VAR
VAR
    state               : Q19_STATE := ST_IDLE;
    rtStart             : R_TRIG;
    edgeStart           : BOOL;
    armed               : BOOL;
    prevManual          : BOOL;
END_VAR

(* rising edge of Start *)
rtStart(CLK := Start);
edgeStart := rtStart.Q;

(* leaving manual mode resets the automatic sequence *)
IF prevManual AND NOT ManualMode THEN
    state := ST_IDLE;
    armed := FALSE;
END_IF
prevManual := ManualMode;

(* all outputs cleared each scan *)
MoveDown        := FALSE;
MoveUp          := FALSE;
MoveLeft        := FALSE;
MoveRight       := FALSE;
ActivateGrip    := FALSE;
ActivateRelease := FALSE;

(* emergency stop: stop every action immediately *)
IF NOT EmergencyStop THEN
    state := ST_IDLE;
    armed := FALSE;
    RETURN;
END_IF

(* ================= manual mode ================= *)
IF ManualMode THEN
    state := ST_IDLE;
    armed := FALSE;

    IF DownButton AND NOT DownLimitSwitch THEN
        MoveDown := TRUE;
    END_IF;
    IF UpButton AND NOT UpLimitSwitch THEN
        MoveUp := TRUE;
    END_IF;
    IF LeftButton AND NOT LeftLimitSwitch THEN
        MoveLeft := TRUE;
    END_IF;
    IF RightButton AND NOT RightLimitSwitch THEN
        MoveRight := TRUE;
    END_IF;
    IF GripButton AND NOT GripLimitSwitch THEN
        ActivateGrip := TRUE;
    END_IF;
    IF ReleaseButton AND NOT ReleaseLimitSwitch THEN
        ActivateRelease := TRUE;
    END_IF;
    RETURN;
END_IF

(* ================= automatic modes ================= *)
(* single step: every Start rising edge releases exactly one action *)
IF SingleStepMode THEN
    IF edgeStart THEN
        armed := NOT armed;
    END_IF
END_IF

(* a finished cycle: continuous restarts by itself, others wait for Start *)
IF state = ST_DONE THEN
    IF ContinuousMode THEN
        state := ST_DOWN1;
    ELSE
        state := ST_IDLE;
        armed := FALSE;
    END_IF
END_IF

CASE state OF
ST_IDLE:
    IF edgeStart AND (SingleCycleMode OR ContinuousMode) THEN
        armed := TRUE;
    END_IF
    IF armed THEN
        state := ST_DOWN1;
    END_IF

ST_DOWN1:
    MoveDown := TRUE;
    IF DownLimitSwitch THEN
        state := ST_GRIP;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

ST_GRIP:
    ActivateGrip := TRUE;
    IF GripLimitSwitch THEN
        state := ST_UP1;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

ST_UP1:
    MoveUp := TRUE;
    IF UpLimitSwitch THEN
        state := ST_RIGHT;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

ST_RIGHT:
    MoveRight := TRUE;
    IF RightLimitSwitch THEN
        state := ST_DOWN2;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

ST_DOWN2:
    MoveDown := TRUE;
    IF DownLimitSwitch THEN
        state := ST_RELEASE;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

ST_RELEASE:
    ActivateRelease := TRUE;
    IF ReleaseLimitSwitch THEN
        state := ST_UP2;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

ST_UP2:
    MoveUp := TRUE;
    IF UpLimitSwitch THEN
        state := ST_LEFT;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

ST_LEFT:
    MoveLeft := TRUE;
    IF LeftLimitSwitch THEN
        armed := FALSE;
        IF SingleStepMode THEN
            state := ST_IDLE;
        ELSE
            state := ST_DONE;
        END_IF
    END_IF

ST_DONE:
    ;

ELSE
    state := ST_IDLE;
END_CASE
