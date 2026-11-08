TYPE ST_Pump :
   STRUCT
      priority : INT;
      selection : BOOL;
      RunComd : BOOL;
   END_STRUCT;
END_TYPE

FUNCTION_BLOCK Q07

VAR_INPUT
    mode : BOOL; // FALSE: Manual, TRUE: Automatic
    start : BOOL;
    stop : BOOL;
END_VAR

VAR_IN_OUT
    pumpGroup : ARRAY[1 .. 5] OF ST_Pump;
END_VAR

VAR
    i : INT;
    j : INT;
    k : INT;
    tempPriority : INT;
    tempIndex : INT;
    enabledState : BOOL;
    sortIndices : ARRAY[1 .. 5] OF INT;
    sortPriorities : ARRAY[1 .. 5] OF INT;
    selectedForRun : ARRAY[1 .. 5] OF BOOL;
END_VAR

VAR
    enabled : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : INT;
WBTEMP_1 : INT;
WBTEMP_2 : INT;
WBTEMP_3 : INT;
WBTEMP_4 : INT;
WBTEMP_5 : BOOL;
WBTEMP_6 : INT;
WBTEMP_7 : INT;
WBTEMP_8 : INT;
WBTEMP_9 : INT;
WBTEMP_10 : INT;
WBTEMP_11 : INT;
WBTEMP_12 : INT;
WBTEMP_13 : INT;
WBTEMP_14 : INT;
WBTEMP_15 : INT;
WBTEMP_16 : BOOL;
WBTEMP_17 : BOOL;
WBTEMP_18 : BOOL;
WBTEMP_19 : BOOL;
WBTEMP_20 : BOOL;
END_VAR


     
i := WBTEMP_0;
j := WBTEMP_1;
k := WBTEMP_2;
tempPriority := WBTEMP_3;
tempIndex := WBTEMP_4;
enabledState := WBTEMP_5;
sortIndices[1] := WBTEMP_6;
sortIndices[2] := WBTEMP_7;
sortIndices[3] := WBTEMP_8;
sortIndices[4] := WBTEMP_9;
sortIndices[5] := WBTEMP_10;
sortPriorities[1] := WBTEMP_11;
sortPriorities[2] := WBTEMP_12;
sortPriorities[3] := WBTEMP_13;
sortPriorities[4] := WBTEMP_14;
sortPriorities[5] := WBTEMP_15;
selectedForRun[1] := WBTEMP_16;
selectedForRun[2] := WBTEMP_17;
selectedForRun[3] := WBTEMP_18;
selectedForRun[4] := WBTEMP_19;
selectedForRun[5] := WBTEMP_20;
    // 1. Enable Latch Logic (Stop Priority)
    IF stop THEN
        enabled := FALSE;
    ELSIF start AND NOT stop THEN
        enabled := TRUE;
    END_IF;

    // Initialize helper arrays
    FOR i := 1 TO 5 DO
        selectedForRun[i] := FALSE;
        // Copy priorities and indices for sorting
        sortPriorities[i] := pumpGroup[i].priority;
        sortIndices[i] := i;
    END_FOR;

    // 2. Mode Logic
    IF enabled THEN
        IF NOT mode THEN
            // Manual Mode: Run if selection is TRUE
            FOR i := 1 TO 5 DO
                IF pumpGroup[i].selection THEN
                    selectedForRun[i] := TRUE;
                ELSE
                    selectedForRun[i] := FALSE;
                END_IF;
            END_FOR;
        ELSE
            // Automatic Mode: Select top 3 by priority
            // Sort indices based on priority (Descending Bubble Sort)
            FOR i := 1 TO 4 DO
                FOR j := 1 TO 5 - i DO
                    IF sortPriorities[j] < sortPriorities[j + 1] THEN
                        // Swap priorities
                        tempPriority := sortPriorities[j];
                        sortPriorities[j] := sortPriorities[j + 1];
                        sortPriorities[j + 1] := tempPriority;
                        
                        // Swap indices
                        tempIndex := sortIndices[j];
                        sortIndices[j] := sortIndices[j + 1];
                        sortIndices[j + 1] := tempIndex;
                    END_IF;
                END_FOR;
            END_FOR;

            // Mark top 3 as selected for run
            FOR i := 1 TO 3 DO
                selectedForRun[sortIndices[i]] := TRUE;
            END_FOR;
        END_IF;
    ELSE
        // Disabled: No pumps selected
        FOR i := 1 TO 5 DO
            selectedForRun[i] := FALSE;
        END_FOR;
    END_IF;

    // 3. Write Output RunComd
    FOR i := 1 TO 5 DO
        pumpGroup[i].RunComd := selectedForRun[i];
    END_FOR;

END_FUNCTION_BLOCK