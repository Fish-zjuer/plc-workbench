FUNCTION_BLOCK FB_WeighbridgeVote
VAR_INPUT
    LoadA : DINT;
    LoadB : DINT;
    LoadC : DINT;
    ReleaseReq : BOOL;
    BarrierReady : BOOL;
END_VAR
VAR_OUTPUT
    PairMask : USINT;
    VotedKg : LREAL;
    LoadFault : BOOL;
    Overload : BOOL;
    ReleasePermit : BOOL;
END_VAR
VAR
    validA : BOOL;
    validB : BOOL;
    validC : BOOL;
    diffAB : DINT;
    diffAC : DINT;
    diffBC : DINT;
    okAB : BOOL;
    okAC : BOOL;
    okBC : BOOL;
    bestDiff : DINT;
    bestMask : USINT;
    found : BOOL;
END_VAR

validA := (LoadA >= 0) AND (LoadA <= 20000);
validB := (LoadB >= 0) AND (LoadB <= 20000);
validC := (LoadC >= 0) AND (LoadC <= 20000);

diffAB := 0;
diffAC := 0;
diffBC := 0;
okAB := FALSE;
okAC := FALSE;
okBC := FALSE;

IF validA AND validB THEN
    diffAB := ABS(LoadA - LoadB);
    IF diffAB <= 200 THEN
        okAB := TRUE;
    END_IF;
END_IF;

IF validA AND validC THEN
    diffAC := ABS(LoadA - LoadC);
    IF diffAC <= 200 THEN
        okAC := TRUE;
    END_IF;
END_IF;

IF validB AND validC THEN
    diffBC := ABS(LoadB - LoadC);
    IF diffBC <= 200 THEN
        okBC := TRUE;
    END_IF;
END_IF;

bestDiff := 0;
bestMask := 0;
found := FALSE;

IF okAB THEN
    bestDiff := diffAB;
    bestMask := 3;
    found := TRUE;
END_IF;

IF okAC THEN
    IF (NOT found) OR (diffAC < bestDiff) THEN
        bestDiff := diffAC;
        bestMask := 5;
        found := TRUE;
    END_IF;
END_IF;

IF okBC THEN
    IF (NOT found) OR (diffBC < bestDiff) THEN
        bestDiff := diffBC;
        bestMask := 6;
        found := TRUE;
    END_IF;
END_IF;

IF found THEN
    PairMask := bestMask;

    IF bestMask = 3 THEN
        VotedKg := (DINT_TO_LREAL(LoadA) + DINT_TO_LREAL(LoadB)) / 2.0;
    ELSIF bestMask = 5 THEN
        VotedKg := (DINT_TO_LREAL(LoadA) + DINT_TO_LREAL(LoadC)) / 2.0;
    ELSE
        VotedKg := (DINT_TO_LREAL(LoadB) + DINT_TO_LREAL(LoadC)) / 2.0;
    END_IF;

    LoadFault := FALSE;
    Overload := VotedKg > 10000.0;
    ReleasePermit := ReleaseReq AND BarrierReady AND NOT Overload;
ELSE
    PairMask := 0;
    VotedKg := 0.0;
    LoadFault := TRUE;
    Overload := FALSE;
    ReleasePermit := FALSE;
END_IF;

END_FUNCTION_BLOCK