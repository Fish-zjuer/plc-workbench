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
    ST_LEFT
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
    stepIndex           : INT := 0;
    autoRunning         : BOOL := FALSE;
    rtStart             : R_TRIG;
    edgeStart           : BOOL;
    lastMode            : INT := 0;   (* 0=manual, 1=step, 2=cycle, 3=continuous *)
    currentMode         : INT;
    modeChanged         : BOOL;
END_VAR

(* determine current mode *)
IF ManualMode THEN
    currentMode := 0;
ELSIF SingleStepMode THEN
    currentMode := 1;
ELSIF SingleCycleMode THEN
    currentMode := 2;
ELSIF ContinuousMode THEN
    currentMode := 3;
ELSE
    currentMode := 0;
END_IF

(* reset sequence on mode change *)
modeChanged := (currentMode <> lastMode);
IF modeChanged THEN
    state := ST_IDLE;
    stepIndex := 0;
    autoRunning := FALSE;
    lastMode := currentMode;
END_IF

(* rising edge of Start *)
rtStart(CLK := Start);
edgeStart := rtStart.Q;

(* emergency stop: highest priority *)
IF NOT EmergencyStop THEN
    MoveDown        := FALSE;
    MoveUp          := FALSE;
    MoveLeft        := FALSE;
    MoveRight       := FALSE;
    ActivateGrip    := FALSE;
    ActivateRelease := FALSE;
    state := ST_IDLE;
    stepIndex := 0;
    autoRunning := FALSE;
    RETURN;
END_IF

(* clear all outputs every scan *)
MoveDown        := FALSE;
MoveUp          := FALSE;
MoveLeft        := FALSE;
MoveRight       := FALSE;
ActivateGrip    := FALSE;
ActivateRelease := FALSE;

(* ================= manual mode ================= *)
IF currentMode = 0 THEN
    state := ST_IDLE;
    stepIndex := 0;
    autoRunning := FALSE;

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
CASE state OF
ST_IDLE:
    IF edgeStart THEN
        (* start the action determined by stepIndex *)
        CASE stepIndex OF
        0: state := ST_DOWN1;
        1: state := ST_GRIP;
        2: state := ST_UP1;
        3: state := ST_RIGHT;
        4: state := ST_DOWN2;
        5: state := ST_RELEASE;
        6: state := ST_UP2;
        7: state := ST_LEFT;
        ELSE state := ST_DOWN1;
        END_CASE;
        IF (currentMode = 2) OR (currentMode = 3) THEN
            autoRunning := TRUE;
        END_IF;
    END_IF

ST_DOWN1:
    MoveDown := TRUE;
    IF DownLimitSwitch THEN
        stepIndex := 1;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSE
            state := ST_GRIP;
        END_IF;
    END_IF

ST_GRIP:
    ActivateGrip := TRUE;
    IF GripLimitSwitch THEN
        stepIndex := 2;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSE
            state := ST_UP1;
        END_IF;
    END_IF

ST_UP1:
    MoveUp := TRUE;
    IF UpLimitSwitch THEN
        stepIndex := 3;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSE
            state := ST_RIGHT;
        END_IF;
    END_IF

ST_RIGHT:
    MoveRight := TRUE;
    IF RightLimitSwitch THEN
        stepIndex := 4;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSE
            state := ST_DOWN2;
        END_IF;
    END_IF

ST_DOWN2:
    MoveDown := TRUE;
    IF DownLimitSwitch THEN
        stepIndex := 5;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSE
            state := ST_RELEASE;
        END_IF;
    END_IF

ST_RELEASE:
    ActivateRelease := TRUE;
    IF ReleaseLimitSwitch THEN
        stepIndex := 6;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSE
            state := ST_UP2;
        END_IF;
    END_IF

ST_UP2:
    MoveUp := TRUE;
    IF UpLimitSwitch THEN
        stepIndex := 7;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSE
            state := ST_LEFT;
        END_IF;
    END_IF

ST_LEFT:
    MoveLeft := TRUE;
    IF LeftLimitSwitch THEN
        stepIndex := 0;
        IF currentMode = 1 THEN
            state := ST_IDLE;
        ELSIF currentMode = 2 THEN
            state := ST_IDLE;
            autoRunning := FALSE;
        ELSE (* currentMode = 3 *)
            state := ST_DOWN1;
        END_IF;
    END_IF

ELSE
    state := ST_IDLE;
END_CASE

END_FUNCTION_BLOCK