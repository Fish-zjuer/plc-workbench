FUNCTION_BLOCK Q20

VAR_INPUT
    Mode : BOOL;
    ForwardButton : BOOL;
    ReverseButton : BOOL;
    SensorFeed : BOOL;
    SensorWash : BOOL;
    SensorWeight : BOOL;
    SensorFiring : BOOL;
    SensorOutput : BOOL;
    washComplete : BOOL;
    weightComplete : BOOL;
    weight : REAL;
    firingComplete : BOOL;
END_VAR

VAR_OUTPUT
    MotorForward : BOOL;
    MotorReverse : BOOL;
    kick : BOOL;
    CompletionLight : BOOL;
    firingTemp : REAL;
END_VAR

VAR
    Step : INT := 0;
    KickHold : BOOL := FALSE;
END_VAR

     
    IF KickHold AND NOT SensorWeight THEN
        KickHold := FALSE;
    END_IF;

    IF NOT Mode THEN
        Step := 0;
        KickHold := FALSE;
        CompletionLight := FALSE;
        firingTemp := 0.0;
        IF ForwardButton AND NOT ReverseButton THEN
            MotorForward := TRUE;
            MotorReverse := FALSE;
        ELSIF ReverseButton AND NOT ForwardButton THEN
            MotorReverse := TRUE;
            MotorForward := FALSE;
        ELSE
            MotorForward := FALSE;
            MotorReverse := FALSE;
        END_IF;
    ELSE
        MotorReverse := FALSE;
        kick := KickHold;
        CASE Step OF
            0:
                MotorForward := FALSE;
                CompletionLight := FALSE;
                IF SensorFeed THEN
                    MotorForward := TRUE;
                    Step := 10;
                END_IF;
            10:
                MotorForward := TRUE;
                IF SensorWash THEN
                    MotorForward := FALSE;
                    Step := 20;
                END_IF;
            20:
                MotorForward := FALSE;
                IF washComplete THEN
                    MotorForward := TRUE;
                    Step := 30;
                END_IF;
            30:
                MotorForward := TRUE;
                IF SensorWeight THEN
                    MotorForward := FALSE;
                    Step := 40;
                END_IF;
            40:
                MotorForward := FALSE;
                IF weightComplete THEN
                    IF weight >= 100.0 AND weight <= 200.0 THEN
                        firingTemp := 500.0 + 0.5 * (weight - 100.0);
                        MotorForward := TRUE;
                        Step := 50;
                    ELSE
                        KickHold := TRUE;
                        Step := 45;
                    END_IF;
                END_IF;
            45:
                MotorForward := FALSE;
                Step := 0;
            50:
                MotorForward := TRUE;
                IF SensorFiring THEN
                    MotorForward := FALSE;
                    Step := 60;
                END_IF;
            60:
                MotorForward := FALSE;
                IF firingComplete THEN
                    MotorForward := TRUE;
                    Step := 70;
                END_IF;
            70:
                MotorForward := TRUE;
                IF SensorOutput THEN
                    MotorForward := FALSE;
                    Step := 80;
                END_IF;
            80:
                MotorForward := FALSE;
                CompletionLight := SensorOutput;
                IF NOT SensorOutput THEN
                    Step := 0;
                END_IF;
            ELSE
                Step := 0;
        END_CASE;
    END_IF;
END_FUNCTION_BLOCK

