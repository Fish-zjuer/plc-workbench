FUNCTION_BLOCK Q15

VAR_INPUT
    estop : BOOL;
    opeMode : BOOL;
    valveAStart : BOOL;
    valveBStart : BOOL;
    valveCStart : BOOL;
    valveDStart : BOOL;
    mixMotorStart : BOOL;
    autoStart : BOOL;
    processMode : BOOL;
    levelSensor : INT;
    mixMotorComplete : BOOL;
END_VAR

VAR_OUTPUT
    valveARun : BOOL;
    valveBRun : BOOL;
    valveCRun : BOOL;
    valveDRun : BOOL;
    mixMotorRun : BOOL;
END_VAR

VAR
    aStartEdge : R_TRIG;
    bStartEdge : R_TRIG;
    cStartEdge : R_TRIG;
    dStartEdge : R_TRIG;
    mStartEdge : R_TRIG;
    autoStartEdge : R_TRIG;
    autoStep : INT;
END_VAR

     
    // Edge detection for buttons
    aStartEdge(CLK := valveAStart);
    bStartEdge(CLK := valveBStart);
    cStartEdge(CLK := valveCStart);
    dStartEdge(CLK := valveDStart);
    mStartEdge(CLK := mixMotorStart);
    autoStartEdge(CLK := autoStart);

    IF NOT estop THEN
        // Emergency stop: all equipment off, sequence reset
        valveARun := FALSE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        autoStep := 0;
    ELSE
        IF NOT opeMode THEN
            // Manual mode: each rising edge toggles corresponding output
            autoStep := 0;

            IF aStartEdge.Q THEN
                valveARun := NOT valveARun;
            END_IF;
            IF bStartEdge.Q THEN
                valveBRun := NOT valveBRun;
            END_IF;
            IF cStartEdge.Q THEN
                valveCRun := NOT valveCRun;
            END_IF;
            IF dStartEdge.Q THEN
                valveDRun := NOT valveDRun;
            END_IF;
            IF mStartEdge.Q THEN
                mixMotorRun := NOT mixMotorRun;
            END_IF;
        ELSE
            // Automatic mode
            IF autoStep = 0 THEN
                // Idle: all outputs off
                valveARun := FALSE;
                valveBRun := FALSE;
                valveCRun := FALSE;
                valveDRun := FALSE;
                mixMotorRun := FALSE;
                IF autoStartEdge.Q THEN
                    autoStep := 1;
                    valveARun := TRUE;
                END_IF;
            ELSIF autoStep = 1 THEN
                // Fill material A until 50 cm
                valveARun := TRUE;
                valveBRun := FALSE;
                valveCRun := FALSE;
                valveDRun := FALSE;
                mixMotorRun := FALSE;
                IF levelSensor >= 50 THEN
                    valveARun := FALSE;
                    valveBRun := TRUE;
                    autoStep := 2;
                END_IF;
            ELSIF autoStep = 2 THEN
                // Fill material B until 80 cm
                valveARun := FALSE;
                valveBRun := TRUE;
                valveCRun := FALSE;
                valveDRun := FALSE;
                mixMotorRun := FALSE;
                IF levelSensor >= 80 THEN
                    valveBRun := FALSE;
                    IF processMode THEN
                        valveCRun := TRUE;
                        autoStep := 3;
                    ELSE
                        mixMotorRun := TRUE;
                        autoStep := 4;
                    END_IF;
                END_IF;
            ELSIF autoStep = 3 THEN
                // Fill material C until 100 cm
                valveARun := FALSE;
                valveBRun := FALSE;
                valveCRun := TRUE;
                valveDRun := FALSE;
                mixMotorRun := FALSE;
                IF levelSensor >= 100 THEN
                    valveCRun := FALSE;
                    mixMotorRun := TRUE;
                    autoStep := 4;
                END_IF;
            ELSIF autoStep = 4 THEN
                // Mixing: wait for complete signal
                valveARun := FALSE;
                valveBRun := FALSE;
                valveCRun := FALSE;
                valveDRun := FALSE;
                mixMotorRun := TRUE;
                IF mixMotorComplete THEN
                    mixMotorRun := FALSE;
                    valveDRun := TRUE;
                    autoStep := 5;
                END_IF;
            ELSE
                // Step 5: deliver through valve D, automatic process ends
                valveARun := FALSE;
                valveBRun := FALSE;
                valveCRun := FALSE;
                mixMotorRun := FALSE;
                valveDRun := TRUE;
                autoStep := 0;
            END_IF;
        END_IF;
    END_IF;

END_FUNCTION_BLOCK