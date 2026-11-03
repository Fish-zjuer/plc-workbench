(* =====================================================================
   Public bank question 20 -- Production Control
   CODESYS-style Structured Text, STruC++ offline syntax subset.
   FB name: Q20   (interface exactly as given in question.md)

   Process: Feed -> Wash -> Weight -> Firing -> Output
   Mode = FALSE : manual (Forward/Reverse buttons, interlocked)
   Mode = TRUE  : automatic sequential cycle

   Unspecified by the task text (my choices, documented, not proven):
   - kick / firingTemp are level outputs of the automated branch;
     kick is dropped again once the rejected item is transported away
     (motor stops) or after the next item is weighed; firingTemp is
     held (last computed value) until a new qualified item is weighed.
   - the manual motor branch overrides the automatic sequence while
     Mode = FALSE; the sequence state is reset on a mode change.
   - "100..200" is read as a decimal magnitude -> weight must be
     >= 100.0 AND <= 200.0; 500..550 degC maps linearly, clamped.
   - weightComplete is only evaluated for the item that caused the
     stop (one-shot per station, gated by the sensor), so a signal
     that stays TRUE does not push the same item through twice.
   ===================================================================== *)

TYPE Q20_STATE :
(
    S_IDLE := 0,        (* waiting for material at loading station          *)
    S_TO_WASH := 1,     (* feeding the item to the cleaning station         *)
    S_AT_WASH := 2,     (* waiting for washComplete                         *)
    S_TO_WEIGHT := 3,   (* feeding the item to the weighing station         *)
    S_AT_WEIGHT := 4,   (* waiting for weightComplete                       *)
    S_TO_FIRING := 5,   (* qualified item, feeding to the firing station    *)
    S_AT_FIRING := 6,   (* waiting for firingComplete                       *)
    S_TO_OUTPUT := 7,   (* feeding the product to the finished goods station*)
    S_AT_OUTPUT := 8     (* product present, completion light on            *)
);
END_TYPE


FUNCTION_BLOCK Q20
VAR_INPUT
    Mode           : BOOL;   (* 0 = manual, 1 = automatic                     *)
    ForwardButton  : BOOL;   (* manual forward rotation button                *)
    ReverseButton  : BOOL;   (* manual reverse rotation button               *)
    SensorFeed     : BOOL;   (* loading station sensor                       *)
    SensorWash     : BOOL;   (* cleaning station sensor                      *)
    SensorWeight   : BOOL;   (* weighing station sensor                      *)
    SensorFiring   : BOOL;   (* firing station sensor                        *)
    SensorOutput   : BOOL;   (* finished goods station sensor                *)
    washComplete   : BOOL;   (* cleaning finished signal                     *)
    weightComplete : BOOL;   (* weighing finished signal                     *)
    weight         : REAL;   (* measured weight                              *)
    firingComplete : BOOL;   (* firing finished signal                       *)
END_VAR
VAR_OUTPUT
    MotorForward   : BOOL;   (* motor forward rotation                       *)
    MotorReverse   : BOOL;   (* motor reverse rotation                       *)
    kick           : BOOL;   (* rejection command                            *)
    CompletionLight: BOOL;   (* product processing complete light            *)
    firingTemp     : REAL;   (* firing temperature                           *)
END_VAR
VAR
    state          : Q20_STATE;   (* automatic sequence state                *)
    prevMode       : BOOL;        (* mode change detection                   *)
    initDone       : BOOL;        (* first scan initialisation               *)
    mfMan, mrMan   : BOOL;        (* scan-level manual commands              *)
    lint           : REAL;        (* local weight copy + clamping            *)
    weightOK       : BOOL;        (* weight in 100..200                      *)
    weightDone     : BOOL;        (* weightComplete seen for this item       *)
    rejectItem     : BOOL;        (* current item rejected                   *)
END_VAR


(* ---- manual commands, interlocked: reverse has priority -------------- *)
mfMan := FALSE;
mrMan := FALSE;
IF NOT Mode THEN
    IF ReverseButton THEN
        mrMan := TRUE;
    ELSIF ForwardButton THEN
        mfMan := TRUE;
    END_IF;
END_IF;

(* ---- outputs default ------------------------------------------------- *)
MotorForward    := FALSE;
MotorReverse    := FALSE;
CompletionLight := FALSE;
IF NOT initDone THEN
    (* first scan: no mode change event, keep sequence at idle *)
    prevMode := Mode;
    initDone := TRUE;
    state    := S_IDLE;
    rejectItem := FALSE;
    weightDone := FALSE;
END_IF;

(* ---- mode change resets the automatic sequence ----------------------- *)
IF Mode <> prevMode THEN
    prevMode   := Mode;
    state      := S_IDLE;
    rejectItem := FALSE;
    weightDone := FALSE;
END_IF;

(* ---- automatic sequence --------------------------------------------- *)
IF Mode THEN
    CASE state OF
    S_IDLE :
        IF SensorFeed THEN
            MotorForward := TRUE;        (* move material to wash station *)
            state := S_TO_WASH;
        END_IF;

    S_TO_WASH :
        IF SensorWash THEN
            state := S_AT_WASH;          (* arrived: motor stops          *)
        ELSE
            MotorForward := TRUE;
        END_IF;

    S_AT_WASH :
        IF washComplete THEN
            MotorForward := TRUE;        (* move material to weighing     *)
            state := S_TO_WEIGHT;
        END_IF;

    S_TO_WEIGHT :
        IF SensorWeight THEN
            state := S_AT_WEIGHT;        (* arrived: motor stops          *)
        ELSE
            MotorForward := TRUE;
        END_IF;

    S_AT_WEIGHT :
        IF weightComplete THEN
            weightDone := TRUE;
            IF (weight >= 100.0) AND (weight <= 200.0) THEN
                weightOK := TRUE;
            ELSE
                weightOK := FALSE;
            END_IF;
            IF weightOK THEN
                (* 100..200 -> 500..550 degC, linear *)
                lint := weight;
                IF lint < 100.0 THEN
                    lint := 100.0;
                END_IF;
                IF lint > 200.0 THEN
                    lint := 200.0;
                END_IF;
                firingTemp := 500.0 + ((lint - 100.0) / 100.0) * 50.0;
                rejectItem := FALSE;
                MotorForward := TRUE;    (* qualified: to firing station  *)
                state := S_TO_FIRING;
            ELSE
                rejectItem := TRUE;      (* unqualified: reject           *)
                MotorForward := FALSE;
                (* stay at the weighing station, item is ejected by kick *)
                state := S_AT_WEIGHT;
            END_IF;
        END_IF;

    S_TO_FIRING :
        IF SensorFiring THEN
            state := S_AT_FIRING;
        ELSE
            MotorForward := TRUE;
        END_IF;

    S_AT_FIRING :
        IF firingComplete THEN
            MotorForward := TRUE;        (* move product to finished area *)
            state := S_TO_OUTPUT;
        END_IF;

    S_TO_OUTPUT :
        IF SensorOutput THEN
            state := S_AT_OUTPUT;        (* arrived: motor stops          *)
        ELSE
            MotorForward := TRUE;
        END_IF;

    S_AT_OUTPUT :
        IF SensorOutput THEN
            CompletionLight := TRUE;     (* product present               *)
        ELSE
            (* product taken away: light off, line is free again        *)
            CompletionLight := FALSE;
            rejectItem := FALSE;
            weightDone := FALSE;
            state := S_IDLE;
        END_IF;

    ELSE
        state := S_IDLE;
    END_CASE;
ELSE
    (* manual mode drives the motor directly *)
    MotorForward := mfMan;
    MotorReverse := mrMan;
END_IF;

(* ---- rejection command --------------------------------------------- *)
(* active for a rejected item at the weighing station, until the item
   is gone (sensor lost) so that the following item starts cleanly      *)
IF Mode AND rejectItem THEN
    kick := TRUE;
    IF NOT SensorWeight THEN
        rejectItem := FALSE;
    END_IF;
ELSE
    kick := FALSE;
END_IF;

END_FUNCTION_BLOCK
