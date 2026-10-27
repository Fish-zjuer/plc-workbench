(* =====================================================================
   公共题库第 08 题：Analog Batch Processing
   主功能块：Q08
   后端：STruC++ 0.7.0 + g++（离线编译/有限检查），非 CODESYS 编译，
        也非形式化验证或实体 PLC 验证。
   ===================================================================== *)

TYPE ST_AnalogChannel :
STRUCT
    enable        : BOOL;   (* 输入字段：通道使能 *)
    hiLIM         : REAL;   (* 输入字段：工程值上限 *)
    loLIM         : REAL;   (* 输入字段：工程值下限 *)
    bipolar       : BOOL;   (* 输入字段：FALSE=单极性 0..27648，TRUE=双极性 -27648..27648 *)
    measuringMode : INT;    (* 输入字段：0 非温度，1 标准温度，2 气候温度 *)
    retVal        : WORD;   (* 输出字段：通道状态码 *)
    outputValue   : REAL;   (* 输出字段：转换结果 *)
END_STRUCT
END_TYPE


FUNCTION_BLOCK Q08
VAR_INPUT
    count : DINT;
END_VAR
VAR_IN_OUT
    analogValues : ARRAY[*] OF INT;
    channels     : ARRAY[*] OF ST_AnalogChannel;
END_VAR
VAR
    i          : DINT;   (* 相对序号，0..count-1 *)
    aLower     : DINT;   (* analogValues 自身下界 *)
    cLower     : DINT;   (* channels 自身下界 *)
    aUpper     : DINT;   (* analogValues 自身上界 *)
    cUpper     : DINT;   (* channels 自身上界 *)
    aIdx       : DINT;   (* 实际访问下标 *)
    cIdx       : DINT;
    nProc      : DINT;   (* 实际处理的通道数 *)
    rawVal     : INT;
    spanRaw    : DINT;
    spanEng    : REAL;
END_VAR


(* ---------- 1) 计算按各自下界对齐时可处理的通道数 ---------- *)
aLower := LOWER_BOUND(analogValues, 1);
aUpper := UPPER_BOUND(analogValues, 1);
cLower := LOWER_BOUND(channels, 1);
cUpper := UPPER_BOUND(channels, 1);

nProc := count;
IF nProc < 0 THEN
    nProc := 0;
END_IF
IF nProc > (aUpper - aLower + 1) THEN
    nProc := aUpper - aLower + 1;
END_IF
IF nProc > (cUpper - cLower + 1) THEN
    nProc := cUpper - cLower + 1;
END_IF

(* ---------- 2) 逐通道处理 ---------- *)
FOR i := 0 TO nProc - 1 DO
    aIdx := aLower + i;
    cIdx := cLower + i;

    (* 只有测量模式 0 的线性换算需要检查限值，温度模式只用 loLIM/hiLIM 做合法性校验 *)
    IF channels[cIdx].enable THEN
        channels[cIdx].retVal      := 16#0000;
        channels[cIdx].outputValue := channels[cIdx].outputValue;  (* 保持原值，除成功换算外不改写 *)

        CASE channels[cIdx].measuringMode OF
        0:
            IF channels[cIdx].hiLIM <= channels[cIdx].loLIM THEN
                channels[cIdx].retVal := 16#8002;
            ELSE
                rawVal  := analogValues[aIdx];
                spanEng := channels[cIdx].hiLIM - channels[cIdx].loLIM;
                IF channels[cIdx].bipolar THEN
                    (* -27648..27648 -> loLIM..hiLIM *)
                    spanRaw := 27648 - (-27648);
                    channels[cIdx].outputValue :=
                        channels[cIdx].loLIM + spanEng * DINT_TO_REAL(rawVal - (-27648)) / DINT_TO_REAL(spanRaw);
                ELSE
                    (* 0..27648 -> loLIM..hiLIM *)
                    spanRaw := 27648 - 0;
                    channels[cIdx].outputValue :=
                        channels[cIdx].loLIM + spanEng * DINT_TO_REAL(rawVal - 0) / DINT_TO_REAL(spanRaw);
                END_IF
            END_IF

        1:
            (* 标准温度：原始值 / 10 *)
            IF channels[cIdx].hiLIM <= channels[cIdx].loLIM THEN
                channels[cIdx].retVal := 16#8002;
            ELSE
                rawVal := analogValues[aIdx];
                channels[cIdx].outputValue := DINT_TO_REAL(rawVal) / 10.0;
            END_IF

        2:
            (* 气候温度：原始值 / 100 *)
            IF channels[cIdx].hiLIM <= channels[cIdx].loLIM THEN
                channels[cIdx].retVal := 16#8002;
            ELSE
                rawVal := analogValues[aIdx];
                channels[cIdx].outputValue := DINT_TO_REAL(rawVal) / 100.0;
            END_IF

        ELSE
            (* 未定义的测量模式 *)
            channels[cIdx].retVal := 16#8001;
        END_CASE
    END_IF
END_FOR

END_FUNCTION_BLOCK
