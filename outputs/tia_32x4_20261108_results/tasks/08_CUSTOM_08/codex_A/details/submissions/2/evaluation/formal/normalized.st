FUNCTION_BLOCK FB_CraneSpeedCheck

   VAR_INPUT
      LeftSpeed10 : INT;
      RightSpeed10 : INT;
      ReferenceSpeed10 : INT;
   END_VAR
   VAR_OUTPUT
      SyncOK : BOOL;
      SyncBad : BOOL;
      Invalid : BOOL;
   END_VAR
   VAR
      ValidInputs : BOOL;
      SyncHolds : BOOL;
      GearHolds : BOOL;
      SideSum : DINT;
      DiffLR : DINT;
      GearDiff : DINT;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
WBTEMP_3 : DINT;
WBTEMP_4 : DINT;
WBTEMP_5 : DINT;
END_VAR

     
ValidInputs := WBTEMP_0;
SyncHolds := WBTEMP_1;
GearHolds := WBTEMP_2;
SideSum := WBTEMP_3;
DiffLR := WBTEMP_4;
GearDiff := WBTEMP_5;
	ValidInputs := (LeftSpeed10 >= 0) AND (LeftSpeed10 <= 100)
	             AND (RightSpeed10 >= 0) AND (RightSpeed10 <= 100)
	             AND (ReferenceSpeed10 > 0) AND (ReferenceSpeed10 <= 100);

	SyncOK := FALSE;
	SyncBad := FALSE;
	Invalid := FALSE;

	IF NOT ValidInputs THEN
	    Invalid := TRUE;
	ELSE
	    SideSum := LeftSpeed10 + RightSpeed10;
	    DiffLR := LeftSpeed10 - RightSpeed10;
	    GearDiff := SideSum - 13 * ReferenceSpeed10;
	    IF DiffLR < 0 THEN
	        DiffLR := -DiffLR;
	    END_IF;
	    IF GearDiff < 0 THEN
	        GearDiff := -GearDiff;
	    END_IF;
	    SyncHolds := (DiffLR <= 1);
	    GearHolds := (GearDiff <= 2);
	    IF SyncHolds AND GearHolds THEN
	        SyncOK := TRUE;
	    ELSE
	        SyncBad := TRUE;
	    END_IF;
	END_IF;
END_FUNCTION_BLOCK