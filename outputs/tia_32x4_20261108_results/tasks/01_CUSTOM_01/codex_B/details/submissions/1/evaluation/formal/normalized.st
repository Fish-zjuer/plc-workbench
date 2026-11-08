FUNCTION_BLOCK FB_ElevatorTarget

  VAR_INPUT
    Enable : BOOL;
    CurrentFloor : INT;
    Direction : INT;
    FullLoad : BOOL;
    CabReq : ARRAY[1 .. 6] OF BOOL;
    HallReq : ARRAY[1 .. 6] OF BOOL;
  END_VAR

  VAR_OUTPUT
    HasTarget : BOOL;
    TargetFloor : INT;
    NextDirection : INT;
  END_VAR

  VAR
    i : INT;
    f : INT;
    best : INT;
    dist : INT;
    upFound : BOOL;
    downFound : BOOL;
    sideFound : BOOL;
    eligible : ARRAY[1 .. 6] OF BOOL;
  END_VAR
VAR_INPUT
WBTEMP_0 : INT;
WBTEMP_1 : INT;
WBTEMP_2 : INT;
WBTEMP_3 : INT;
WBTEMP_4 : BOOL;
WBTEMP_5 : BOOL;
WBTEMP_6 : BOOL;
WBTEMP_7 : BOOL;
WBTEMP_8 : BOOL;
WBTEMP_9 : BOOL;
WBTEMP_10 : BOOL;
WBTEMP_11 : BOOL;
WBTEMP_12 : BOOL;
END_VAR


     
i := WBTEMP_0;
f := WBTEMP_1;
best := WBTEMP_2;
dist := WBTEMP_3;
upFound := WBTEMP_4;
downFound := WBTEMP_5;
sideFound := WBTEMP_6;
eligible[1] := WBTEMP_7;
eligible[2] := WBTEMP_8;
eligible[3] := WBTEMP_9;
eligible[4] := WBTEMP_10;
eligible[5] := WBTEMP_11;
eligible[6] := WBTEMP_12;
    f := CurrentFloor;
    IF (f < 1) OR (f > 6) THEN
        IF f < 1 THEN
            f := 1;
        ELSE
            f := 6;
        END_IF;
    END_IF;

    FOR i := 1 TO 6 DO
        eligible[i] := CabReq[i] OR (HallReq[i] AND NOT FullLoad);
    END_FOR;

    HasTarget := FALSE;
    TargetFloor := CurrentFloor;
    NextDirection := 0;
    upFound := FALSE;
    downFound := FALSE;
    sideFound := FALSE;
    best := 0;

    IF Enable THEN
        IF eligible[f] THEN
            HasTarget := TRUE;
            TargetFloor := f;
            NextDirection := 0;
        ELSE
            IF Direction >= 0 THEN
                FOR i := (f + 1) TO 6 DO
                    IF eligible[i] THEN
                        TargetFloor := i;
                        upFound := TRUE;
                        EXIT;
                    END_IF;
                END_FOR;
            END_IF;
            IF Direction <= 0 THEN
                FOR i := (f - 1) TO 1 BY -1 DO
                    IF eligible[i] THEN
                        TargetFloor := i;
                        downFound := TRUE;
                        EXIT;
                    END_IF;
                END_FOR;
            END_IF;

            IF Direction = 1 THEN
                IF upFound THEN
                    HasTarget := TRUE;
                ELSE
                    FOR i := 1 TO (f - 1) DO
                        IF eligible[i] THEN
                            best := i;
                        END_IF;
                    END_FOR;
                    IF best <> 0 THEN
                        TargetFloor := best;
                        HasTarget := TRUE;
                    END_IF;
                END_IF;
            ELSIF Direction = -1 THEN
                IF downFound THEN
                    HasTarget := TRUE;
                ELSE
                    FOR i := 6 TO (f + 1) BY -1 DO
                        IF eligible[i] THEN
                            best := i;
                        END_IF;
                    END_FOR;
                    IF best <> 0 THEN
                        TargetFloor := best;
                        HasTarget := TRUE;
                    END_IF;
                END_IF;
            ELSE
                dist := 7;
                FOR i := 1 TO 6 DO
                    IF eligible[i] AND (i <> f) THEN
                        IF ABS(i - f) < dist THEN
                            dist := ABS(i - f);
                            best := i;
                            sideFound := TRUE;
                        END_IF;
                    END_IF;
                END_FOR;
                IF sideFound THEN
                    HasTarget := TRUE;
                    TargetFloor := best;
                END_IF;
            END_IF;
        END_IF;
    END_IF;

    IF HasTarget THEN
        IF TargetFloor > f THEN
            NextDirection := 1;
        ELSIF TargetFloor < f THEN
            NextDirection := -1;
        ELSE
            NextDirection := 0;
        END_IF;
    ELSE
        TargetFloor := CurrentFloor;
        NextDirection := 0;
    END_IF;
END_FUNCTION_BLOCK
