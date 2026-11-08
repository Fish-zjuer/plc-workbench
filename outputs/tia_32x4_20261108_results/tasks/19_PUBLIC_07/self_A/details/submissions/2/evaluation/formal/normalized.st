TYPE ST_Pump :
   STRUCT
      priority : INT;
      selection : BOOL;
      RunComd : BOOL;
   END_STRUCT;
END_TYPE

FUNCTION_BLOCK Q07

VAR_INPUT
    mode : BOOL;
    start : BOOL;
    stop : BOOL;
END_VAR

VAR_IN_OUT
    pumpGroup : ARRAY[1 .. 5] OF ST_Pump;
END_VAR

VAR
    enabled : BOOL;
END_VAR

VAR
    i : INT;
    j : INT;
    tmpPump : ST_Pump;
    order : ARRAY[1 .. 5] OF INT;
    rank : INT;
END_VAR
VAR_INPUT
WBTEMP_0 : INT;
WBTEMP_1 : INT;
WBTEMP_2 : INT;
WBTEMP_3 : BOOL;
WBTEMP_4 : BOOL;
WBTEMP_5 : INT;
WBTEMP_6 : INT;
WBTEMP_7 : INT;
WBTEMP_8 : INT;
WBTEMP_9 : INT;
WBTEMP_10 : INT;
END_VAR


     
i := WBTEMP_0;
j := WBTEMP_1;
tmpPump.priority := WBTEMP_2;
tmpPump.selection := WBTEMP_3;
tmpPump.RunComd := WBTEMP_4;
order[1] := WBTEMP_5;
order[2] := WBTEMP_6;
order[3] := WBTEMP_7;
order[4] := WBTEMP_8;
order[5] := WBTEMP_9;
rank := WBTEMP_10;
    // 运行使能锁存：stop 优先关闭，start 且非 stop 时开启，其余保持
    IF stop THEN
        enabled := FALSE;
    ELSIF start THEN
        enabled := TRUE;
    END_IF;

    IF NOT enabled THEN
        // 未使能：全部停止
        FOR i := 1 TO 5 DO
            pumpGroup[i].RunComd := FALSE;
        END_FOR;

    ELSIF NOT mode THEN
        // 手动模式：按选择位运行
        FOR i := 1 TO 5 DO
            IF pumpGroup[i].selection THEN
                pumpGroup[i].RunComd := TRUE;
            ELSE
                pumpGroup[i].RunComd := FALSE;
            END_IF;
        END_FOR;

    ELSE
        // 自动模式：按优先级降序排列（稳定排序，不写入 priority/selection）
        FOR i := 1 TO 5 DO
            order[i] := i;
        END_FOR;

        FOR i := 1 TO 4 DO
            FOR j := 1 TO 5 - i DO
                IF pumpGroup[order[j]].priority < pumpGroup[order[j + 1]].priority THEN
                    rank := order[j];
                    order[j] := order[j + 1];
                    order[j + 1] := rank;
                END_IF;
            END_FOR;
        END_FOR;

        // 先全部停止，再启用优先级最高的三台
        FOR i := 1 TO 5 DO
            pumpGroup[i].RunComd := FALSE;
        END_FOR;

        FOR i := 1 TO 3 DO
            pumpGroup[order[i]].RunComd := TRUE;
        END_FOR;
    END_IF;

END_FUNCTION_BLOCK