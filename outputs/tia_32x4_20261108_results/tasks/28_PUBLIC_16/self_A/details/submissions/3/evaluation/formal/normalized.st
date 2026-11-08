FUNCTION_BLOCK Q16

VAR_INPUT
    processLength : USINT;
    sensor1 : BOOL;
    sensor2 : BOOL;
    sensor3 : BOOL;
    sensor4 : BOOL;
    sensor5 : BOOL;
    station1Start : BOOL;
    station2Complete : BOOL;
    station3Complete : BOOL;
    station4Complete : BOOL;
    processSequence : ARRAY[1 .. 8] OF USINT;
END_VAR

VAR_OUTPUT
    conveyorLeft : BOOL;
    conveyorRight : BOOL;
END_VAR

VAR
    state : INT;
    cursor : INT;
    currentStation : INT;
    targetStation : INT;
    moveDir : INT;
    lastStart : BOOL;
    lastComplete2 : BOOL;
    lastComplete3 : BOOL;
    lastComplete4 : BOOL;
END_VAR

VAR
    startEdge : BOOL;
    completeEdge : BOOL;
    targetSensor : BOOL;
    stationCount : INT;
    targetValid : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
WBTEMP_2 : BOOL;
WBTEMP_3 : INT;
WBTEMP_4 : BOOL;
END_VAR


     
startEdge := WBTEMP_0;
completeEdge := WBTEMP_1;
targetSensor := WBTEMP_2;
stationCount := WBTEMP_3;
targetValid := WBTEMP_4;
    // 默认输出
    conveyorLeft := FALSE;
    conveyorRight := FALSE;

    // 启动上升沿
    startEdge := station1Start AND NOT lastStart;
    lastStart := station1Start;

    // 各站处理完成上升沿
    completeEdge := (station2Complete AND NOT lastComplete2)
                     OR (station3Complete AND NOT lastComplete3)
                     OR (station4Complete AND NOT lastComplete4);
    lastComplete2 := station2Complete;
    lastComplete3 := station3Complete;
    lastComplete4 := station4Complete;

    // 序列长度限幅
    IF (processLength < 1) THEN
        stationCount := 1;
    ELSIF (processLength > 8) THEN
        stationCount := 8;
    ELSE
        stationCount := USINT_TO_INT(processLength);
    END_IF;

    CASE state OF
        0:  // 空闲：等待 1# 站有料且按下启动，立即选首目标
            cursor := 1;
            currentStation := 1;
            moveDir := 0;
            targetStation := 1;
            IF sensor1 AND startEdge THEN
                targetStation := USINT_TO_INT(processSequence[1]);
                IF (targetStation < 1) OR (targetStation > 5) THEN
                    targetStation := 5;
                END_IF;
                IF (targetStation > currentStation) THEN
                    moveDir := 1;
                ELSIF (targetStation < currentStation) THEN
                    moveDir := -1;
                ELSE
                    moveDir := 0;
                END_IF;
                IF (moveDir = 0) THEN
                    state := 20;
                ELSE
                    state := 15;
                END_IF;
            END_IF;

        10: // 选定下一目标，计算方向
            targetValid := FALSE;
            IF (cursor >= 1) AND (cursor <= 8) THEN
                targetStation := USINT_TO_INT(processSequence[cursor]);
                IF (targetStation >= 1) AND (targetStation <= 5) THEN
                    targetValid := TRUE;
                END_IF;
            END_IF;
            IF NOT targetValid THEN
                targetStation := 5;
            END_IF;

            IF (targetStation > currentStation) THEN
                moveDir := 1;
            ELSIF (targetStation < currentStation) THEN
                moveDir := -1;
            ELSE
                moveDir := 0;
            END_IF;

            IF (moveDir = 0) THEN
                state := 20;
            ELSE
                state := 15;
            END_IF;

        15: // 运输中：按方向单向运行，目标传感器到达即停
            IF (moveDir > 0) THEN
                conveyorRight := TRUE;
                conveyorLeft := FALSE;
            ELSIF (moveDir < 0) THEN
                conveyorLeft := TRUE;
                conveyorRight := FALSE;
            ELSE
                conveyorLeft := FALSE;
                conveyorRight := FALSE;
            END_IF;

            targetSensor := FALSE;
            CASE targetStation OF
                1: targetSensor := sensor1;
                2: targetSensor := sensor2;
                3: targetSensor := sensor3;
                4: targetSensor := sensor4;
                5: targetSensor := sensor5;
            ELSE
                targetSensor := FALSE;
            END_CASE;

            IF targetSensor THEN
                conveyorLeft := FALSE;
                conveyorRight := FALSE;
                moveDir := 0;
                currentStation := targetStation;
                state := 20;
            END_IF;

        20: // 到达目标站，停带等待处理
            conveyorLeft := FALSE;
            conveyorRight := FALSE;
            moveDir := 0;

            IF (currentStation >= 5) THEN
                state := 30;
            ELSE
                IF completeEdge THEN
                    IF (cursor < stationCount) THEN
                        cursor := cursor + 1;
                        state := 10;
                        // 立即在同拍选下一目标并驱动
                        targetValid := FALSE;
                        IF (cursor >= 1) AND (cursor <= 8) THEN
                            targetStation := USINT_TO_INT(processSequence[cursor]);
                            IF (targetStation >= 1) AND (targetStation <= 5) THEN
                                targetValid := TRUE;
                            END_IF;
                        END_IF;
                        IF NOT targetValid THEN
                            targetStation := 5;
                        END_IF;
                        IF (targetStation > currentStation) THEN
                            moveDir := 1;
                        ELSIF (targetStation < currentStation) THEN
                            moveDir := -1;
                        ELSE
                            moveDir := 0;
                        END_IF;
                        IF (moveDir = 0) THEN
                            state := 20;
                        ELSE
                            state := 15;
                            IF (moveDir > 0) THEN
                                conveyorRight := TRUE;
                                conveyorLeft := FALSE;
                            ELSE
                                conveyorLeft := TRUE;
                                conveyorRight := FALSE;
                            END_IF;
                        END_IF;
                    ELSE
                        state := 30;
                    END_IF;
                END_IF;
            END_IF;

        30: // 完成，停带；1# 站无料且空位后复位
            conveyorLeft := FALSE;
            conveyorRight := FALSE;
            moveDir := 0;
            IF NOT sensor1 THEN
                cursor := 1;
                currentStation := 1;
                targetStation := 1;
                state := 0;
            END_IF;

    ELSE
        state := 0;
    END_CASE;

    // 互锁：不允许同时左右
    IF conveyorLeft AND conveyorRight THEN
        conveyorLeft := FALSE;
        conveyorRight := FALSE;
    END_IF;

END_FUNCTION_BLOCK