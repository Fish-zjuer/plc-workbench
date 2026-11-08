FUNCTION_BLOCK FB_RollGeometry

VAR_INPUT
    Reset : BOOL;
    InitialD : LREAL;
    Receiving : BOOL;
    EncoderDelta : DINT;
    SpeedMpm : LREAL;
END_VAR

VAR_OUTPUT
    StoredLength : LREAL;
    Diameter : LREAL;
    MotorRPM : LREAL;
    LimitHit : BOOL;
    Error : BOOL;
END_VAR

VAR
    initialized : BOOL;
END_VAR

VAR
    PI : LREAL;
    CoreD : LREAL;
    MaxD : LREAL;
    Thickness : LREAL;
    Lmax : LREAL;
    init : BOOL;
    valid : BOOL;
    deltaL : LREAL;
    raw : LREAL;
    tmpSpeed : LREAL;
END_VAR
VAR_INPUT
WBTEMP_0 : LREAL;
WBTEMP_1 : LREAL;
WBTEMP_2 : LREAL;
WBTEMP_3 : LREAL;
WBTEMP_4 : LREAL;
WBTEMP_5 : BOOL;
WBTEMP_6 : BOOL;
WBTEMP_7 : LREAL;
WBTEMP_8 : LREAL;
WBTEMP_9 : LREAL;
END_VAR


     
PI := WBTEMP_0;
CoreD := WBTEMP_1;
MaxD := WBTEMP_2;
Thickness := WBTEMP_3;
Lmax := WBTEMP_4;
init := WBTEMP_5;
valid := WBTEMP_6;
deltaL := WBTEMP_7;
raw := WBTEMP_8;
tmpSpeed := WBTEMP_9;
    PI := 3.141592653589793;
    CoreD := 76.0;
    MaxD := 140.0;
    Thickness := 0.135;
    Lmax := PI * (MaxD * MaxD - CoreD * CoreD) / (4.0 * Thickness);

    init := (NOT initialized) OR Reset;

    valid := (SpeedMpm >= -15.0) AND (SpeedMpm <= 15.0)
             AND (EncoderDelta >= 0) AND (EncoderDelta <= 1000000)
             AND ((NOT init) OR ((InitialD >= CoreD) AND (InitialD <= MaxD)));

    IF NOT valid THEN
        Error := TRUE;
        MotorRPM := 0.0;
        LimitHit := FALSE;
        StoredLength := StoredLength;
        Diameter := Diameter;
    ELSE
        Error := FALSE;
        IF init THEN
            StoredLength := PI * (InitialD * InitialD - CoreD * CoreD) / (4.0 * Thickness);
            Diameter := InitialD;
            MotorRPM := 0.0;
            LimitHit := FALSE;
            initialized := TRUE;
        ELSE
            deltaL := DINT_TO_LREAL(EncoderDelta) * PI * 50.0 / 1024.0;
            IF Receiving THEN
                raw := StoredLength + deltaL;
            ELSE
                raw := StoredLength - deltaL;
            END_IF;

            IF raw < 0.0 THEN
                LimitHit := TRUE;
                StoredLength := 0.0;
            ELSIF raw > Lmax THEN
                LimitHit := TRUE;
                StoredLength := Lmax;
            ELSE
                LimitHit := FALSE;
                StoredLength := raw;
            END_IF;

            Diameter := SQRT(CoreD * CoreD + 4.0 * Thickness * StoredLength / PI);

            tmpSpeed := SpeedMpm * 1000.0 * 50.0 / (PI * Diameter);
            IF tmpSpeed > 6000.0 THEN
                MotorRPM := 6000.0;
            ELSIF tmpSpeed < -6000.0 THEN
                MotorRPM := -6000.0;
            ELSE
                MotorRPM := tmpSpeed;
            END_IF;
        END_IF;
    END_IF;
END_FUNCTION_BLOCK