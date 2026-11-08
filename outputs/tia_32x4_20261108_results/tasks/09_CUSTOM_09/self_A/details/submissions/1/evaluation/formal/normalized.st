FUNCTION_BLOCK FB_SpectrometerQualification

VAR_INPUT
    Maintenance : BOOL;
    CalibDone : BOOL;
    MeasureReq : BOOL;
END_VAR

VAR_OUTPUT
    State : USINT;
    CalibReq : BOOL;
    MaintLamp : BOOL;
    MeasurePermit : BOOL;
END_VAR

VAR
    statState : USINT;
    statInitialized : BOOL;
END_VAR

     
    // 初始化：首个扫描前 State=0, CalibReq=TRUE, MaintLamp=FALSE, MeasurePermit=FALSE
    IF NOT statInitialized THEN
        statState := 0;
        statInitialized := TRUE;
    END_IF;

    // 基于扫描前状态的单次转换
    IF Maintenance THEN
        statState := 2;
    ELSIF statState = 2 THEN
        // 退出维护的同扫描先回等待标定，即使 CalibDone=TRUE
        statState := 0;
    ELSIF statState = 0 THEN
        IF CalibDone THEN
            statState := 1;
        ELSE
            statState := 0;
        END_IF;
    ELSIF statState = 1 THEN
        statState := 1;
    ELSE
        // 非法状态复位到等待标定
        statState := 0;
    END_IF;

    // 输出映射基于更新后的状态
    State := statState;
    CalibReq := (statState = 0);
    MaintLamp := (statState = 2);
    MeasurePermit := MeasureReq AND (statState = 1);
END_FUNCTION_BLOCK