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
      ValidA : BOOL;
      ValidB : BOOL;
      ValidC : BOOL;
      DiffAB : DINT;
      DiffAC : DINT;
      DiffBC : DINT;
      HasAB : BOOL;
      HasAC : BOOL;
      HasBC : BOOL;
      HasPair : BOOL;
      BestDiff : DINT;
      SelMask : USINT;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
WBTEMP_3 : DINT;
WBTEMP_4 : DINT;
WBTEMP_5 : DINT;
WBTEMP_6 : BOOL;
WBTEMP_7 : BOOL;
WBTEMP_8 : BOOL;
WBTEMP_9 : BOOL;
WBTEMP_10 : DINT;
WBTEMP_11 : USINT;
END_VAR
 
     
ValidA := WBTEMP_0;
ValidB := WBTEMP_1;
ValidC := WBTEMP_2;
DiffAB := WBTEMP_3;
DiffAC := WBTEMP_4;
DiffBC := WBTEMP_5;
HasAB := WBTEMP_6;
HasAC := WBTEMP_7;
HasBC := WBTEMP_8;
HasPair := WBTEMP_9;
BestDiff := WBTEMP_10;
SelMask := WBTEMP_11;
   // Range validation (0..20000 kg) before computing differences
   ValidA := (LoadA >= 0) AND (LoadA <= 20000);
   ValidB := (LoadB >= 0) AND (LoadB <= 20000);
   ValidC := (LoadC >= 0) AND (LoadC <= 20000);

   // Differences computed only on valid channels; DINT wide enough for 0..20000
   DiffAB := 0;
   DiffAC := 0;
   DiffBC := 0;
   IF ValidA AND ValidB THEN
      IF LoadA >= LoadB THEN
         DiffAB := LoadA - LoadB;
      ELSE
         DiffAB := LoadB - LoadA;
      END_IF;
   END_IF;
   IF ValidA AND ValidC THEN
      IF LoadA >= LoadC THEN
         DiffAC := LoadA - LoadC;
      ELSE
         DiffAC := LoadC - LoadA;
      END_IF;
   END_IF;
   IF ValidB AND ValidC THEN
      IF LoadB >= LoadC THEN
         DiffBC := LoadB - LoadC;
      ELSE
         DiffBC := LoadC - LoadB;
      END_IF;
   END_IF;

   // Candidate consistent pairs (<=200 kg)
   HasAB := ValidA AND ValidB AND (DiffAB <= 200);
   HasAC := ValidA AND ValidC AND (DiffAC <= 200);
   HasBC := ValidB AND ValidC AND (DiffBC <= 200);

   // Select minimum difference; ties favour AB < AC < BC
   HasPair := FALSE;
   BestDiff := 0;
   SelMask := 0;

   IF HasAB THEN
      HasPair := TRUE;
      BestDiff := DiffAB;
      SelMask := 3;
   END_IF;

   IF HasAC THEN
      IF (NOT HasPair) OR (DiffAC < BestDiff) THEN
         HasPair := TRUE;
         BestDiff := DiffAC;
         SelMask := 5;
      END_IF;
   END_IF;

   IF HasBC THEN
      IF (NOT HasPair) OR (DiffBC < BestDiff) THEN
         HasPair := TRUE;
         BestDiff := DiffBC;
         SelMask := 6;
      END_IF;
   END_IF;

   // Outputs
   IF HasPair THEN
      PairMask := SelMask;
      CASE SelMask OF
         3:
            VotedKg := (DINT_TO_LREAL(LoadA) + DINT_TO_LREAL(LoadB)) / 2.0;
         5:
            VotedKg := (DINT_TO_LREAL(LoadA) + DINT_TO_LREAL(LoadC)) / 2.0;
         6:
            VotedKg := (DINT_TO_LREAL(LoadB) + DINT_TO_LREAL(LoadC)) / 2.0;
         ELSE
            VotedKg := 0.0;
      END_CASE;
      LoadFault := FALSE;
      Overload := (VotedKg > 10000.0);
      ReleasePermit := ReleaseReq AND BarrierReady AND (NOT Overload);
   ELSE
      PairMask := 0;
      VotedKg := 0.0;
      LoadFault := TRUE;
      Overload := FALSE;
      ReleasePermit := FALSE;
   END_IF;
END_FUNCTION_BLOCK