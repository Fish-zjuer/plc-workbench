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

  计时实现说明：本离线后端不提供 RTRIG，且 TON 的复位行为不可靠，
  因此改用时间戳（读系统毫秒时间）自行计算连续加热时长与保护保持时长。
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
    T_OVERHEAT_LIMIT_MS : TIME := T#5S;  (* 连续加热上限 *)
    T_OVERHEAT_HOLD_MS  : TIME := T#3S;  (* 过热保护保持时间 *)
    TEMP_MIN_VALID      : REAL := 0.0;   (* 有效温度下限（含） *)
    TEMP_MAX_VALID      : REAL := 100.0; (* 有效温度上限（含） *)
END_VAR
VAR
    tNow         : TIME;         (* 本扫描时间戳 *)
    tHeatStart   : TIME;         (* 本次连续加热开始时刻 *)
    tOverStart   : TIME;         (* 本次过热保护开始时刻 *)
    tHeatDur     : TIME;         (* 已连续加热时长 *)
    tOverDur     : TIME;         (* 保护已保持时长 *)
    xHeatRunPrev : BOOL := FALSE; (* 上一扫描加热器状态 *)
    xOverPrev    : BOOL := FALSE; (* 上一扫描过热保护状态 *)
    xHeatRise    : BOOL;          (* 加热器上升沿 *)
    xOverRise    : BOOL;          (* 过热保护上升沿 *)
    xSensorFault : BOOL;          (* 传感器故障 *)
    xHeaterReq   : BOOL;          (* 温度调节请求 *)
    xHeaterOn    : BOOL;          (* 内部加热器命令 *)
    xOverheat    : BOOL;          (* 过热保护置位 *)
END_VAR

(* 本扫描时间戳 *)
tNow := TIME();

(* ---------- 1) 传感器故障判断 ---------- *)
xSensorFault := (TemperatureSensorInput < TEMP_MIN_VALID)
             OR (TemperatureSensorInput > TEMP_MAX_VALID);

(* ---------- 6) 状态显示 ---------- *)
CurrentTemperature := TemperatureSensorInput;
SetTempDisplay     := SetTemperature;

(* ---------- 2/3/4) 温度比较，产生加热请求 ---------- *)
IF TemperatureSensorInput < SetTemperature THEN
    xHeaterReq := TRUE;
ELSIF TemperatureSensorInput > SetTemperature THEN
    xHeaterReq := FALSE;
ELSE
    (* 相等：题面未定义，保持原有请求 *)
    xHeaterReq := xHeaterReq;
END_IF

(* ---------- 边沿检测（基于上一扫描保存的状态） ---------- *)
xHeatRise := xHeaterOn AND NOT xHeatRunPrev;
xOverRise := xOverheat AND NOT xOverPrev;

(* ---------- 5a) 连续加热计时 ---------- *)
IF xHeaterOn THEN
    IF xHeatRise THEN
        (* 加热器刚启动：从本时刻开始计连续工作时间 *)
        tHeatStart := tNow;
    END_IF
    tHeatDur := tNow - tHeatStart;
ELSE
    (* 加热器未工作：连续工作时间清零 *)
    tHeatStart := tNow;
    tHeatDur   := T#0S;
END_IF

(* 连续加热达到 5s：触发过热保护并立即关闭加热器 *)
IF xHeaterOn AND (tHeatDur >= T_OVERHEAT_LIMIT_MS) THEN
    xOverheat := TRUE;
END_IF

(* 加热器重新启动时清除旧的过热状态 *)
IF xHeatRise THEN
    xOverheat := FALSE;
END_IF

(* ---------- 5b) 过热保护保持计时 ---------- *)
IF xOverheat THEN
    IF xOverRise THEN
        tOverStart := tNow;
    END_IF
    tOverDur := tNow - tOverStart;
    (* 保持满 3s 后解除保护 *)
    IF tOverDur >= T_OVERHEAT_HOLD_MS THEN
        xOverheat := FALSE;
    END_IF
ELSE
    tOverStart := tNow;
    tOverDur   := T#0S;
END_IF

(* ---------- 输出合成 ---------- *)
IF xSensorFault THEN
    (* 7) 传感器故障时强制关加热器 *)
    xHeaterOn := FALSE;
ELSIF xOverheat THEN
    (* 5) 过热保护时强制关加热器 *)
    xHeaterOn := FALSE;
ELSE
    xHeaterOn := xHeaterReq;
END_IF

(* 保存本扫描状态，供下一扫描比较边沿 *)
xHeatRunPrev := xHeaterOn;
xOverPrev    := xOverheat;

OverheatProtection := xOverheat;
HeaterStatus       := xHeaterOn;
HeaterOutput       := xHeaterOn;
END_FUNCTION_BLOCK
