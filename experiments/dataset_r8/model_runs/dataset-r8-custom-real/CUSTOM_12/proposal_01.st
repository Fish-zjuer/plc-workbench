FUNCTION_BLOCK FB_BuoyPowerBudget
VAR_INPUT
    Enable : BOOL;
    BudgetW : UINT;
    NeedSensor : BOOL;
    NeedHeater : BOOL;
    NeedRadio : BOOL;
    MandatorySensor : BOOL;
END_VAR
VAR_OUTPUT
    SelectedMask : USINT;
    SensorOn : BOOL;
    HeaterOn : BOOL;
    RadioOn : BOOL;
    PowerW : UINT;
    Score : USINT;
    BudgetShortage : BOOL;
    Error : BOOL;
END_VAR
VAR
    bestFound : BOOL;
    bestMask : USINT;
    bestPower : UINT;
    bestScore : USINT;
    candMask : USINT;
    candPower : UINT;
    candScore : USINT;
    candBit1 : BOOL;
    candBit2 : BOOL;
    candBit4 : BOOL;
    feasible : BOOL;
    m : USINT;
END_VAR

(* Always start each scan with zero/FALSE outputs. *)
SelectedMask := 0;
SensorOn := FALSE;
HeaterOn := FALSE;
RadioOn := FALSE;
PowerW := 0;
Score := 0;
BudgetShortage := FALSE;
Error := FALSE;

IF NOT Enable THEN
    (* Disabled has priority: all outputs remain zero/FALSE. *)
ELSIF BudgetW > 200 THEN
    (* Illegal budget. *)
    Error := TRUE;
ELSIF MandatorySensor AND BudgetW < 40 THEN
    (* Mandatory sensor cannot be powered without exceeding budget. *)
    BudgetShortage := TRUE;
ELSE
    bestFound := FALSE;
    bestMask := 0;
    bestPower := 0;
    bestScore := 0;

    FOR m := 0 TO 7 DO
        candMask := m;
        candBit1 := ((candMask MOD 2) = 1);
        candBit2 := ((candMask MOD 4) >= 2);
        candBit4 := (candMask >= 4);

        candPower := 0;
        candScore := 0;

        IF candBit1 THEN
            candPower := candPower + 40;
            candScore := candScore + 7;
        END_IF;
        IF candBit2 THEN
            candPower := candPower + 70;
            candScore := candScore + 10;
        END_IF;
        IF candBit4 THEN
            candPower := candPower + 60;
            candScore := candScore + 9;
        END_IF;

        feasible := TRUE;

        IF candBit1 AND NOT (NeedSensor OR MandatorySensor) THEN
            feasible := FALSE;
        END_IF;
        IF candBit2 AND NOT NeedHeater THEN
            feasible := FALSE;
        END_IF;
        IF candBit4 AND NOT NeedRadio THEN
            feasible := FALSE;
        END_IF;
        IF candPower > BudgetW THEN
            feasible := FALSE;
        END_IF;
        IF MandatorySensor AND NOT candBit1 THEN
            feasible := FALSE;
        END_IF;

        IF feasible THEN
            IF NOT bestFound THEN
                bestFound := TRUE;
                bestMask := candMask;
                bestPower := candPower;
                bestScore := candScore;
            ELSIF candScore > bestScore THEN
                bestMask := candMask;
                bestPower := candPower;
                bestScore := candScore;
            ELSIF candScore = bestScore THEN
                IF candPower < bestPower THEN
                    bestMask := candMask;
                    bestPower := candPower;
                    bestScore := candScore;
                ELSIF candPower = bestPower THEN
                    IF candMask < bestMask THEN
                        bestMask := candMask;
                        bestPower := candPower;
                        bestScore := candScore;
                    END_IF;
                END_IF;
            END_IF;
        END_IF;
    END_FOR;

    SelectedMask := bestMask;
    SensorOn := ((bestMask MOD 2) = 1);
    HeaterOn := ((bestMask MOD 4) >= 2);
    RadioOn := (bestMask >= 4);
    PowerW := bestPower;
    Score := bestScore;
    BudgetShortage := FALSE;
    Error := FALSE;
END_IF;

END_FUNCTION_BLOCK