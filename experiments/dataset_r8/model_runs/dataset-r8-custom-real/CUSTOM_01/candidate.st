FUNCTION_BLOCK FB_ElevatorTarget
VAR_INPUT
  Enable : BOOL;
  CurrentFloor : INT;
  Direction : INT;
  FullLoad : BOOL;
  CabReq : ARRAY[1..6] OF BOOL;
  HallReq : ARRAY[1..6] OF BOOL;
END_VAR
VAR_OUTPUT
  HasTarget : BOOL;
  TargetFloor : INT;
  NextDirection : INT;
END_VAR
VAR
  i : INT;
  j : INT;
  found : BOOL;
  best : INT;
  bestDist : INT;
  d : INT;
  anyEligible : BOOL;
END_VAR

anyEligible := FALSE;
FOR i := 1 TO 6 DO
  IF CabReq[i] OR (HallReq[i] AND NOT FullLoad) THEN
    anyEligible := TRUE;
  END_IF;
END_FOR;

HasTarget := FALSE;
TargetFloor := CurrentFloor;
NextDirection := 0;

IF Enable AND anyEligible THEN
  IF CabReq[CurrentFloor] OR (HallReq[CurrentFloor] AND NOT FullLoad) THEN
    HasTarget := TRUE;
    TargetFloor := CurrentFloor;
    NextDirection := 0;
  ELSE
    found := FALSE;
    best := 0;
    bestDist := 32767;

    IF Direction = 1 THEN
      FOR i := CurrentFloor + 1 TO 6 DO
        IF CabReq[i] OR (HallReq[i] AND NOT FullLoad) THEN
          IF NOT found THEN
            best := i;
            found := TRUE;
          END_IF;
        END_IF;
      END_FOR;

      IF NOT found THEN
        FOR i := 1 TO CurrentFloor - 1 DO
          j := CurrentFloor - i;
          IF CabReq[j] OR (HallReq[j] AND NOT FullLoad) THEN
            IF NOT found THEN
              best := j;
              found := TRUE;
            END_IF;
          END_IF;
        END_FOR;
      END_IF;

    ELSIF Direction = -1 THEN
      FOR i := 1 TO CurrentFloor - 1 DO
        j := CurrentFloor - i;
        IF CabReq[j] OR (HallReq[j] AND NOT FullLoad) THEN
          IF NOT found THEN
            best := j;
            found := TRUE;
          END_IF;
        END_IF;
      END_FOR;

      IF NOT found THEN
        FOR i := CurrentFloor + 1 TO 6 DO
          IF CabReq[i] OR (HallReq[i] AND NOT FullLoad) THEN
            IF NOT found THEN
              best := i;
              found := TRUE;
            END_IF;
          END_IF;
        END_FOR;
      END_IF;

    ELSE
      FOR i := 1 TO 6 DO
        IF CabReq[i] OR (HallReq[i] AND NOT FullLoad) THEN
          d := i - CurrentFloor;
          IF d < 0 THEN
            d := -d;
          END_IF;

          IF (NOT found) OR (d < bestDist) OR ((d = bestDist) AND (i < best)) THEN
            best := i;
            bestDist := d;
            found := TRUE;
          END_IF;
        END_IF;
      END_FOR;
    END_IF;

    IF found THEN
      HasTarget := TRUE;
      TargetFloor := best;

      IF TargetFloor > CurrentFloor THEN
        NextDirection := 1;
      ELSIF TargetFloor < CurrentFloor THEN
        NextDirection := -1;
      ELSE
        NextDirection := 0;
      END_IF;
    ELSE
      HasTarget := FALSE;
      TargetFloor := CurrentFloor;
      NextDirection := 0;
    END_IF;
  END_IF;
END_IF;
END_FUNCTION_BLOCK