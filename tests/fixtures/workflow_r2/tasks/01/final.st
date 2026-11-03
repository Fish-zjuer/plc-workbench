(*
  Q01 - Automated Filling Line Control
  公共题库第 01 题候选实现（CODESYS Structured Text 风格）

  阶段状态机：
    IDLE(0)      等待 bottleSensor 检测到瓶子
    CLEANING(1)  Pump_Motor = TRUE，等待 cleaningConfirmButton
    FILLING(2)   Filling_Valve = TRUE，等待 fillingConfirmButton
    CAPPING(3)   Capping_Machine = TRUE，等待 cappingConfirmButton
    PACKING(4)   Packing_Machine = TRUE，等待 packingConfirmButton
    DONE(5)      Completion_Light = TRUE，等待 finishedButton 复位

  题面未定义的细节（自行取定，见最终说明）：
    - 确认按钮按电平判定：在该阶段内按钮为 TRUE 即推进。
    - 一个周期结束后回到 IDLE，需重新等待 bottleSensor。
*)

TYPE Q01_Phase :
(
    Q01_IDLE     := 0,
    Q01_CLEANING := 1,
    Q01_FILLING  := 2,
    Q01_CAPPING  := 3,
    Q01_PACKING  := 4,
    Q01_DONE     := 5
);
END_TYPE

FUNCTION_BLOCK Q01
VAR_INPUT
    bottleSensor           : BOOL;   (* 检测到瓶子 *)
    cleaningConfirmButton  : BOOL;   (* 清洗完成确认 *)
    fillingConfirmButton   : BOOL;   (* 灌装完成确认 *)
    cappingConfirmButton   : BOOL;   (* 封盖完成确认 *)
    packingConfirmButton   : BOOL;   (* 包装完成确认 *)
    finishedButton         : BOOL;   (* 取走瓶子/复位 *)
END_VAR

VAR_OUTPUT
    Pump_Motor       : BOOL;   (* 清洗泵电机 *)
    Filling_Valve    : BOOL;   (* 灌装阀 *)
    Capping_Machine  : BOOL;   (* 封盖机 *)
    Packing_Machine  : BOOL;   (* 包装机 *)
    Completion_Light : BOOL;   (* 包装完成指示灯 *)
END_VAR

VAR
    Phase : Q01_Phase := Q01_IDLE;   (* 当前工艺阶段 *)
END_VAR

(* ---------- 阶段推进 ---------- *)
CASE Phase OF
    Q01_IDLE:
        IF bottleSensor THEN
            Phase := Q01_CLEANING;
        END_IF;

    Q01_CLEANING:
        IF cleaningConfirmButton THEN
            Phase := Q01_FILLING;
        END_IF;

    Q01_FILLING:
        IF fillingConfirmButton THEN
            Phase := Q01_CAPPING;
        END_IF;

    Q01_CAPPING:
        IF cappingConfirmButton THEN
            Phase := Q01_PACKING;
        END_IF;

    Q01_PACKING:
        IF packingConfirmButton THEN
            Phase := Q01_DONE;
        END_IF;

    Q01_DONE:
        IF finishedButton THEN
            Phase := Q01_IDLE;
        END_IF;

ELSE
    Phase := Q01_IDLE;
END_CASE

(* ---------- 输出映射：各阶段唯一执行机构 ---------- *)
Pump_Motor       := (Phase = Q01_CLEANING);
Filling_Valve    := (Phase = Q01_FILLING);
Capping_Machine  := (Phase = Q01_CAPPING);
Packing_Machine  := (Phase = Q01_PACKING);
Completion_Light := (Phase = Q01_DONE);

END_FUNCTION_BLOCK
