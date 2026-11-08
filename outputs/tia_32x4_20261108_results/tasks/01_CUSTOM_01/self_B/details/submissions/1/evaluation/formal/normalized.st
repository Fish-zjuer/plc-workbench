FUNCTION_BLOCK FB_ElevatorTarget
TITLE = Elevator Direction-biased Target Selection
AUTHOR : Siemens_TIA_Portal_V21_SCL

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
    Eligible : ARRAY[1 .. 6] OF BOOL;
    FoundCurrent : BOOL;
    BestAbove : INT;
    BestBelow : INT;
    DistAbove : INT;
    DistBelow : INT;
    TempDist : INT;
    MinDist : INT;
    CandidateFloor : INT;
END_VAR
VAR_INPUT
WBTEMP_0 : INT;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
WBTEMP_3 : BOOL;
WBTEMP_4 : BOOL;
WBTEMP_5 : BOOL;
WBTEMP_6 : BOOL;
WBTEMP_7 : BOOL;
WBTEMP_8 : INT;
WBTEMP_9 : INT;
WBTEMP_10 : INT;
WBTEMP_11 : INT;
WBTEMP_12 : INT;
WBTEMP_13 : INT;
WBTEMP_14 : INT;
END_VAR


     
i := WBTEMP_0;
Eligible[1] := WBTEMP_1;
Eligible[2] := WBTEMP_2;
Eligible[3] := WBTEMP_3;
Eligible[4] := WBTEMP_4;
Eligible[5] := WBTEMP_5;
Eligible[6] := WBTEMP_6;
FoundCurrent := WBTEMP_7;
BestAbove := WBTEMP_8;
BestBelow := WBTEMP_9;
DistAbove := WBTEMP_10;
DistBelow := WBTEMP_11;
TempDist := WBTEMP_12;
MinDist := WBTEMP_13;
CandidateFloor := WBTEMP_14;
    // Initialize outputs
    HasTarget := FALSE;
    TargetFloor := CurrentFloor;
    NextDirection := 0;

    // If not enabled, return immediately
    IF NOT Enable THEN
        RETURN;
    END_IF;

    // Build eligibility array E
    // A floor i is eligible when CabReq[i] OR (HallReq[i] AND NOT FullLoad)
    FOR i := 1 TO 6 DO
        Eligible[i] := CabReq[i] OR (HallReq[i] AND NOT FullLoad);
    END_FOR;

    // Check if any eligible request exists
    // We can iterate again or use flags during selection logic.
    // Requirement 3: If no eligible request exists, set HasTarget=FALSE...
    // This will be handled by the selection logic resulting in no target found.

    // Requirement 3: Priority to Current Floor
    IF Eligible[CurrentFloor] THEN
        HasTarget := TRUE;
        TargetFloor := CurrentFloor;
        NextDirection := 0;
        RETURN;
    END_IF;

    // If we reach here, CurrentFloor is not eligible.
    // We need to find the best target based on Direction.

    // Initialize search variables
    BestAbove := 0; // 0 means none found
    BestBelow := 0; // 0 means none found
    
    // Scan floors 1 to 6 to find nearest above and below
    FOR i := 1 TO 6 DO
        IF Eligible[i] THEN
            IF i > CurrentFloor THEN
                // Is it closer than current BestAbove?
                IF BestAbove = 0 THEN
                    BestAbove := i;
                ELSE
                    IF i < BestAbove THEN
                        BestAbove := i;
                    END_IF;
                END_IF;
            ELSIF i < CurrentFloor THEN
                // Is it closer than current BestBelow? (Larger index is closer to CurrentFloor from below)
                IF BestBelow = 0 THEN
                    BestBelow := i;
                ELSE
                    IF i > BestBelow THEN
                        BestBelow := i;
                    END_IF;
                END_IF;
            END_IF;
        END_IF;
    END_FOR;

    // Selection Logic based on Direction
    IF Direction = 1 THEN
        // Up: Nearest above. If none, nearest below.
        IF BestAbove <> 0 THEN
            TargetFloor := BestAbove;
            HasTarget := TRUE;
        ELSIF BestBelow <> 0 THEN
            TargetFloor := BestBelow;
            HasTarget := TRUE;
        END_IF;
    ELSIF Direction = -1 THEN
        // Down: Nearest below. If none, nearest above.
        IF BestBelow <> 0 THEN
            TargetFloor := BestBelow;
            HasTarget := TRUE;
        ELSIF BestAbove <> 0 THEN
            TargetFloor := BestAbove;
            HasTarget := TRUE;
        END_IF;
    ELSE
        // Direction = 0 (Idle): Nearest on either side. Tie break toward lower floor.
        IF BestAbove <> 0 AND BestBelow <> 0 THEN
            DistAbove := BestAbove - CurrentFloor;
            DistBelow := CurrentFloor - BestBelow;
            
            IF DistAbove < DistBelow THEN
                TargetFloor := BestAbove;
                HasTarget := TRUE;
            ELSIF DistBelow < DistAbove THEN
                TargetFloor := BestBelow;
                HasTarget := TRUE;
            ELSE
                // Equal distance, tie break toward lower floor
                TargetFloor := BestBelow;
                HasTarget := TRUE;
            END_IF;
        ELSIF BestAbove <> 0 THEN
            TargetFloor := BestAbove;
            HasTarget := TRUE;
        ELSIF BestBelow <> 0 THEN
            TargetFloor := BestBelow;
            HasTarget := TRUE;
        END_IF;
    END_IF;

    // Calculate NextDirection if target found
    IF HasTarget THEN
        IF TargetFloor > CurrentFloor THEN
            NextDirection := 1;
        ELSIF TargetFloor < CurrentFloor THEN
            NextDirection := -1;
        ELSE
            NextDirection := 0;
        END_IF;
    END_IF;

END_FUNCTION_BLOCK