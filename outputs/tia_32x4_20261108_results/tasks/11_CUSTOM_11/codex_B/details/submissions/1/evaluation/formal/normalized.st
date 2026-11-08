FUNCTION_BLOCK FB_WeighbridgeVote
  VERSION : '0.1'

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
    bestMask : USINT;
    bestDiff : DINT;
  END_VAR

     
    validA := (LoadA >= 0) AND (LoadA <= 20000);
    validB := (LoadB >= 0) AND (LoadB <= 20000);
    validC := (LoadC >= 0) AND (LoadC <= 20000);

    IF LoadA >= LoadB THEN
        diffAB := LoadA - LoadB;
    ELSE
        diffAB := LoadB - LoadA;
    END_IF;
    IF LoadA >= LoadC THEN
        diffAC := LoadA - LoadC;
    ELSE
        diffAC := LoadC - LoadA;
    END_IF;
    IF LoadB >= LoadC THEN
        diffBC := LoadB - LoadC;
    ELSE
        diffBC := LoadC - LoadB;
    END_IF;

    okAB := validA AND validB AND (diffAB <= 200);
    okAC := validA AND validC AND (diffAC <= 200);
    okBC := validB AND validC AND (diffBC <= 200);

    bestMask := 0;
    bestDiff := 2147483647;

    IF okAB THEN
        bestMask := 3;
        bestDiff := diffAB;
    END_IF;
    IF okAC AND (diffAC < bestDiff) THEN
        bestMask := 5;
        bestDiff := diffAC;
    END_IF;
    IF okBC AND (diffBC < bestDiff) THEN
        bestMask := 6;
        bestDiff := diffBC;
    END_IF;

    IF bestMask = 0 THEN
        PairMask := 0;
        VotedKg := 0.0;
        LoadFault := TRUE;
        Overload := FALSE;
        ReleasePermit := FALSE;
    ELSE
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
    END_IF;
END_FUNCTION_BLOCK

