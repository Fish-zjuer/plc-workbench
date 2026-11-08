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
    i : INT;
    mask : USINT;
    allowedS : BOOL;
    allowedH : BOOL;
    allowedR : BOOL;
    p : UINT;
    s : USINT;
    feasible : BOOL;
    validBudget : BOOL;
    bestFound : BOOL;
    bestMask : USINT;
    bestPower : UINT;
    bestScore : USINT;
    bitS : BOOL;
    bitH : BOOL;
    bitR : BOOL;
    maskBit : USINT;
END_VAR
VAR_INPUT
WBTEMP_0 : INT;
WBTEMP_1 : USINT;
WBTEMP_2 : BOOL;
WBTEMP_3 : BOOL;
WBTEMP_4 : BOOL;
WBTEMP_5 : UINT;
WBTEMP_6 : USINT;
WBTEMP_7 : BOOL;
WBTEMP_8 : BOOL;
WBTEMP_9 : BOOL;
WBTEMP_10 : USINT;
WBTEMP_11 : UINT;
WBTEMP_12 : USINT;
WBTEMP_13 : BOOL;
WBTEMP_14 : BOOL;
WBTEMP_15 : BOOL;
WBTEMP_16 : USINT;
END_VAR


     
i := WBTEMP_0;
mask := WBTEMP_1;
allowedS := WBTEMP_2;
allowedH := WBTEMP_3;
allowedR := WBTEMP_4;
p := WBTEMP_5;
s := WBTEMP_6;
feasible := WBTEMP_7;
validBudget := WBTEMP_8;
bestFound := WBTEMP_9;
bestMask := WBTEMP_10;
bestPower := WBTEMP_11;
bestScore := WBTEMP_12;
bitS := WBTEMP_13;
bitH := WBTEMP_14;
bitR := WBTEMP_15;
maskBit := WBTEMP_16;
    // Default outputs each scan
    SelectedMask := 0;
    SensorOn := FALSE;
    HeaterOn := FALSE;
    RadioOn := FALSE;
    PowerW := 0;
    Score := 0;
    BudgetShortage := FALSE;
    Error := FALSE;

    // Budget validity 0..200 (BudgetW is UINT, so lower bound is 0)
    validBudget := (BudgetW <= 200);

    IF NOT Enable THEN
        Error := FALSE;
        BudgetShortage := FALSE;
    ELSIF NOT validBudget THEN
        Error := TRUE;
        BudgetShortage := FALSE;
    ELSE
        Error := FALSE;

        IF MandatorySensor AND (BudgetW < 40) THEN
            BudgetShortage := TRUE;
            SelectedMask := 0;
            PowerW := 0;
            Score := 0;
        ELSE
            BudgetShortage := FALSE;

            // Eligible loads per request and mandatory-sensor flag
            allowedS := (NeedSensor OR MandatorySensor);
            allowedH := NeedHeater;
            allowedR := NeedRadio;

            // Enumerate subsets 0..7, global optimum
            bestFound := FALSE;
            bestMask := 0;
            bestPower := 0;
            bestScore := 0;

            FOR i := 0 TO 7 DO
                mask := INT_TO_USINT(i);
                feasible := TRUE;

                // Decode bits
                maskBit := mask AND 1;
                bitS := (maskBit <> 0);
                maskBit := mask AND 2;
                bitH := (maskBit <> 0);
                maskBit := mask AND 4;
                bitR := (maskBit <> 0);

                // Mask must only contain eligible bits
                IF bitS AND NOT allowedS THEN
                    feasible := FALSE;
                END_IF;
                IF bitH AND NOT allowedH THEN
                    feasible := FALSE;
                END_IF;
                IF bitR AND NOT allowedR THEN
                    feasible := FALSE;
                END_IF;

                // Power and score for this subset
                p := 0;
                s := 0;
                IF bitS THEN
                    p := p + 40;
                    s := s + 7;
                END_IF;
                IF bitH THEN
                    p := p + 70;
                    s := s + 10;
                END_IF;
                IF bitR THEN
                    p := p + 60;
                    s := s + 9;
                END_IF;

                // Budget feasibility
                IF p > BudgetW THEN
                    feasible := FALSE;
                END_IF;

                // Mandatory sensor constraint
                IF MandatorySensor AND NOT bitS THEN
                    feasible := FALSE;
                END_IF;

                // Selection: max score, then min power, then min mask
                IF feasible THEN
                    IF NOT bestFound THEN
                        bestFound := TRUE;
                        bestMask := mask;
                        bestPower := p;
                        bestScore := s;
                    ELSIF s > bestScore THEN
                        bestMask := mask;
                        bestPower := p;
                        bestScore := s;
                    ELSIF s = bestScore THEN
                        IF p < bestPower THEN
                            bestMask := mask;
                            bestPower := p;
                            bestScore := s;
                        ELSIF p = bestPower THEN
                            IF mask < bestMask THEN
                                bestMask := mask;
                                bestPower := p;
                                bestScore := s;
                            END_IF;
                        END_IF;
                    END_IF;
                END_IF;
            END_FOR;

            SelectedMask := bestMask;
            PowerW := bestPower;
            Score := bestScore;
        END_IF;
    END_IF;

    // Map mask bits to outputs
    maskBit := SelectedMask AND 1;
    SensorOn := (maskBit <> 0);
    maskBit := SelectedMask AND 2;
    HeaterOn := (maskBit <> 0);
    maskBit := SelectedMask AND 4;
    RadioOn := (maskBit <> 0);
END_FUNCTION_BLOCK