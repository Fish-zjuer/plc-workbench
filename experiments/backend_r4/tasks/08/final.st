(* =====================================================================
   公共题库第 08 题：Analog Batch Processing
   主功能块：Q08
   后端：STruC++ 0.7.0 + g++（离线编译/有限检查），非 CODESYS 编译，
        也非形式化验证或实体 PLC 验证。

   说明：接口严格保留原题 count : DINT（输入）、
         analogValues : ARRAY[*] OF INT（输入输出）、
         channels : ARRAY[*] OF ST_AnalogChannel（输入输出）。
         未用固定长度数组或具体类型替代 ARRAY[*] / VARIANT。
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
    i          : DINT;   (* 相对序号 0..nProc-1 *)
    aLower     : DINT;
    cLower     : DINT;
    aLen       : DINT;
    cLen       : DINT;
    nProc      : DINT;
    aIdx       : DINT;
    cIdx       : DINT;
    rawVal     : INT;
    spanEng    : REAL;
    limValid   : BOOL;
END_VAR


(* ---------- 1) 各自下界对齐，并裁剪处理个数 ---------- *)
aLower := LOWER_BOUND(analogValues, 1);
cLower := LOWER_BOUND(channels, 1);
aLen   := UPPER_BOUND(analogValues, 1) - aLower + 1;
cLen   := UPPER_BOUND(channels, 1) - cLower + 1;

nProc := count;
IF nProc > aLen THEN
    nProc := aLen;
END_IF
IF nProc > cLen THEN
    nProc := cLen;
END_IF

(* ---------- 2) 逐通道处理 ---------- *)
FOR i := 0 TO nProc - 1 DO
    aIdx := aLower + i;
    cIdx := cLower + i;

    IF channels[cIdx].enable THEN
        rawVal   := analogValues[aIdx];
        limValid := channels[cIdx].hiLIM > channels[cIdx].loLIM;

        IF channels[cIdx].measuringMode = 0 THEN
            (* 非温度线性换算 *)
            IF NOT limValid THEN
                channels[cIdx].retVal := 16#8002;
            ELSIF channels[cIdx].bipolar THEN
                (* -27648..27648 -> loLIM..hiLIM *)
                spanEng := channels[cIdx].hiLIM - channels[cIdx].loLIM;
                channels[cIdx].outputValue :=
                    channels[cIdx].loLIM + spanEng * INT_TO_REAL(rawVal + 27648) / 55296.0;
                channels[cIdx].retVal := 16#0000;
            ELSE
                (* 0..27648 -> loLIM..hiLIM *)
                spanEng := channels[cIdx].hiLIM - channels[cIdx].loLIM;
                channels[cIdx].outputValue :=
                    channels[cIdx].loLIM + spanEng * INT_TO_REAL(rawVal) / 27648.0;
                channels[cIdx].retVal := 16#0000;
            END_IF
        ELSIF channels[cIdx].measuringMode = 1 THEN
            (* 标准温度：原始值的 1/10 *)
            IF NOT limValid THEN
                channels[cIdx].retVal := 16#8002;
            ELSE
                channels[cIdx].outputValue := INT_TO_REAL(rawVal) / 10.0;
                channels[cIdx].retVal := 16#0000;
            END_IF
        ELSIF channels[cIdx].measuringMode = 2 THEN
            (* 气候温度：原始值的 1/100 *)
            IF NOT limValid THEN
                channels[cIdx].retVal := 16#8002;
            ELSE
                channels[cIdx].outputValue := INT_TO_REAL(rawVal) / 100.0;
                channels[cIdx].retVal := 16#0000;
            END_IF
        ELSE
            (* 未定义的测量模式 *)
            channels[cIdx].retVal := 16#8001;
        END_IF
    END_IF
END_FOR

END_FUNCTION_BLOCK
