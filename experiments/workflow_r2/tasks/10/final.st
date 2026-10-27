(*
  公共题库第 10 题：温度控制逻辑 (Temperature Logic Control)
  主功能块：Q10
  说明：离线 ST 单元，仅做编译/有限用例检查，不代表 CODESYS 编译或功能安全验证。
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
    xSensorFault : BOOL;          (* 传感器故障 *)
    xHeaterReq   : BOOL := FALSE; (* 温度调节请求（相等时保持） *)
    xHeaterOn    : BOOL := FALSE; (* 内部加热器命令 *)
    xOverheat    : BOOL := FALSE; (* 过热保护置位锁存 *)
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

(* ---------- 5a) 连续加热计时 ---------- *)
IF xHeaterOn THEN
    IF NOT xHeatRunPrev THEN
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
(* 注意：此处必须在同一扫描内记录保护开始时刻，避免保持期从下一扫描才起算 *)
IF xHeaterOn AND (tHeatDur >= T_OVERHEAT_LIMIT_MS) THEN
    xOverheat  := TRUE;
    tOverStart := tNow;
    tOverDur   := T#0S;
END_IF

(* ---------- 5b) 过热保护保持计时 ---------- *)
(* 保护一旦置位，必须独立保持满 3s 才可解除，不因加热器关闭而清零 *)
IF xOverheat THEN
    tOverDur := tNow - tOverStart;
    IF tOverDur >= T_OVERHEAT_HOLD_MS THEN
        xOverheat  := FALSE;
        tOverStart := tNow;
        tOverDur   := T#0S;
    END_IF;
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

OverheatProtection := xOverheat;
HeaterStatus       := xHeaterOn;
HeaterOutput       := xHeaterOn;
END_FUNCTION_BLOCK
