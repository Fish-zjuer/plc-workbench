(*
  公共题库第 10 题：温度控制逻辑 (Temperature Logic Control)
  主功能块：Q10
  说明：离线 ST 单元，仅做编译/有限用例检查，不代表 CODESYS 编译或功能安全验证。

  需求映射：
  1) 通过 TemperatureSensorInput 读取温度
  2/3/4) 实际温度 < 设定温度 -> 开加热器；实际温度 > 设定温度 -> 关加热器
          （等于设定温度时保持原有输出，题面未定义，见总结）
  5) 加热器连续加热超过 5s -> 触发过热保护，强制关加热器；
     过热保护需等待 3s 才能解除
  6) 状态指示：CurrentTemperature / SetTempDisplay / HeaterStatus / OverheatProtection
  7) TemperatureSensorInput < 0.0 或 > 100.0 -> 传感器故障，强制关加热器
*)

FUNCTION_BLOCK Q10
VAR_INPUT
    TemperatureSensorInput : REAL;   (* 实际温度 *)
    SetTemperature         : REAL;   (* 设定温度 *)
END_VAR
VAR_OUTPUT
    CurrentTemperature : REAL;       (* 当前温度显示 *)
    SetTempDisplay     : REAL;       (* 设定温度显示 *)
    HeaterStatus       : BOOL;       (* 加热器状态显示 *)
    OverheatProtection : BOOL;       (* 过热保护状态显示 *)
    HeaterOutput       : BOOL;       (* 加热器控制输出 *)
END_VAR
VAR CONSTANT
    T_OVERHEAT_LIMIT  : TIME := T#5S;  (* 连续加热上限 *)
    T_OVERHEAT_HOLD   : TIME := T#3S;  (* 过热保护保持时间 *)
    TEMP_MIN_VALID    : REAL := 0.0;   (* 有效温度下限（含） *)
    TEMP_MAX_VALID    : REAL := 100.0; (* 有效温度上限（含） *)
END_VAR
VAR
    tonHeatRun  : TON;   (* 连续加热计时 *)
    tonOverheat : TON;   (* 过热保护保持计时 *)
    rtTemp      : RTRIG; (* 加热器启动沿检测，用于清零累加计时 *)
    rtOverheat  : RTRIG; (* 过热保护触发沿检测，用于清零保持计时 *)
    xSensorFault     : BOOL; (* 传感器故障 *)
    xHeaterRequest   : BOOL; (* 温度调节请求 *)
    xHeaterOn        : BOOL; (* 内部加热器命令 *)
    xOverheat        : BOOL; (* 过热保护置位 *)
END_VAR

(* ---------- 1) 传感器故障判断（REAL 需排除 NaN 的写法在本子集不保证可用，
   仅按题面阈值判断） ---------- *)
xSensorFault := (TemperatureSensorInput < TEMP_MIN_VALID)
             OR (TemperatureSensorInput > TEMP_MAX_VALID);

(* ---------- 6) 状态显示 ---------- *)
CurrentTemperature := TemperatureSensorInput;
SetTempDisplay     := SetTemperature;

(* ---------- 2/3/4) 温度比较，产生加热请求 ---------- *)
IF TemperatureSensorInput < SetTemperature THEN
    xHeaterRequest := TRUE;
ELSIF TemperatureSensorInput > SetTemperature THEN
    xHeaterRequest := FALSE;
ELSE
    (* 相等：题面未定义，保持原有请求 *)
    xHeaterRequest := xHeaterRequest;
END_IF

(* ---------- 5) 过热保护：加热器连续工作计时 ---------- *)
tonHeatRun(IN := xHeaterOn,
           PT := T_OVERHEAT_LIMIT);

rtTemp(CLK := xHeaterOn);
IF rtTemp.Q THEN
    (* 加热器刚启动，重新开始累计连续工作时间 *)
    tonHeatRun(IN := FALSE, PT := T_OVERHEAT_LIMIT);
    xOverheat := FALSE;
END_IF

IF tonHeatRun.Q THEN
    xOverheat := TRUE;
END_IF

(* 过热保护保持计时：保护被触发后至少 3s 才能解除 *)
tonOverheat(IN := xOverheat,
            PT := T_OVERHEAT_HOLD);

rtOverheat(CLK := xOverheat);
IF rtOverheat.Q THEN
    tonOverheat(IN := FALSE, PT := T_OVERHEAT_HOLD);
END_IF

IF xOverheat AND tonOverheat.Q THEN
    xOverheat := FALSE;
END_IF

(* ---------- 输出合成 ---------- *)
IF xSensorFault THEN
    (* 7) 传感器故障时强制关加热器 *)
    xHeaterOn := FALSE;
ELSIF xOverheat THEN
    (* 5) 过热保护时强制关加热器 *)
    xHeaterOn := FALSE;
ELSE
    xHeaterOn := xHeaterRequest;
END_IF

OverheatProtection := xOverheat;
HeaterStatus       := xHeaterOn;
HeaterOutput       := xHeaterOn;
END_FUNCTION_BLOCK
