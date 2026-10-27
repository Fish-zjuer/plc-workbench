(*
  Q15 - Material Proportioning Process Control
  原题接口：estop, opeMode, valveAStart..valveDStart, mixMotorStart,
            autoStart, processMode, levelSensor(INT), mixMotorComplete
  输出：valveARun, valveBRun, valveCRun, valveDRun, mixMotorRun
  题面未定义的细节（本实现的选择）：
    - 自动流程的步序内部状态机，autoStart 取上升沿启动；自动流程结束后
      再按 autoStart 上升沿可重新开始。
    - 自动流程中“自动结束”的判定：混合完成后打开阀门 D 且流程回到空闲；
      阀门 D 由手动按钮再次按下时才关闭。
    - 液位阈值判定采用 >=。
    - 急停（estop=FALSE）优先：所有输出立即为 FALSE，并复位自动步序。
    - 手动模式切换会清除自动步序；手动按钮均为上升沿翻转。
*)

FUNCTION_BLOCK Q15
VAR_INPUT
    estop           : BOOL;   (* FALSE: 急停触发 *)
    opeMode         : BOOL;   (* FALSE: 手动, TRUE: 自动 *)
    valveAStart     : BOOL;
    valveBStart     : BOOL;
    valveCStart     : BOOL;
    valveDStart     : BOOL;
    mixMotorStart   : BOOL;
    autoStart       : BOOL;
    processMode     : BOOL;
    levelSensor     : INT;    (* 液位 cm *)
    mixMotorComplete: BOOL;
END_VAR
VAR_OUTPUT
    valveARun       : BOOL;
    valveBRun       : BOOL;
    valveCRun       : BOOL;
    valveDRun       : BOOL;
    mixMotorRun     : BOOL;
END_VAR
VAR
    (* 手动模式：按钮上升沿翻转对应设备 *)
    rtA             : R_TRIG;
    rtB             : R_TRIG;
    rtC             : R_TRIG;
    rtD             : R_TRIG;
    rtMix           : R_TRIG;
    (* 手动输出保持 *)
    manA            : BOOL;
    manB            : BOOL;
    manC            : BOOL;
    manD            : BOOL;
    manMix          : BOOL;
    (* 自动流程 *)
    rtAuto          : R_TRIG;
    rtComplete      : R_TRIG;
    autoStep        : INT;    (* 0 空闲 *)
    autoMixDone     : BOOL;
END_VAR

(* ---- 边沿检测 ---- *)
rtA(CLK := valveAStart);
rtB(CLK := valveBStart);
rtC(CLK := valveCStart);
rtD(CLK := valveDStart);
rtMix(CLK := mixMotorStart);
rtAuto(CLK := autoStart);
rtComplete(CLK := mixMotorComplete);

(* ---- 急停：最高优先级，立即停止全部设备并复位流程 ---- *)
IF NOT estop THEN
    manA := FALSE;
    manB := FALSE;
    manC := FALSE;
    manD := FALSE;
    manMix := FALSE;
    autoStep := 0;
    autoMixDone := FALSE;
    valveARun := FALSE;
    valveBRun := FALSE;
    valveCRun := FALSE;
    valveDRun := FALSE;
    mixMotorRun := FALSE;
    RETURN;
END_IF

(* ================= 手动模式 ================= *)
IF NOT opeMode THEN
    autoStep := 0;
    autoMixDone := FALSE;

    IF rtA.Q THEN manA := NOT manA; END_IF;
    IF rtB.Q THEN manB := NOT manB; END_IF;
    IF rtC.Q THEN manC := NOT manC; END_IF;
    IF rtD.Q THEN manD := NOT manD; END_IF;
    IF rtMix.Q THEN manMix := NOT manMix; END_IF;

    valveARun := manA;
    valveBRun := manB;
    valveCRun := manC;
    valveDRun := manD;
    mixMotorRun := manMix;
    RETURN;
END_IF

(* ================= 自动模式 ================= *)
(* 进入自动模式时忽略手动保持量 *)
manA := FALSE;
manB := FALSE;
manC := FALSE;
manD := FALSE;
manMix := FALSE;

(* 启动 / 重启自动流程 *)
IF autoStep = 0 AND rtAuto.Q THEN
    autoStep := 10;
    autoMixDone := FALSE;
END_IF

(* 步序推进 *)
CASE autoStep OF
    0:  (* 空闲 *)
        valveARun := FALSE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;

    10: (* 开阀门 A 进料 *)
        valveARun := TRUE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        IF levelSensor >= 50 THEN
            autoStep := 20;
        END_IF

    20: (* 关 A 开 B *)
        valveARun := FALSE;
        valveBRun := TRUE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        IF levelSensor >= 80 THEN
            autoStep := 30;
        END_IF

    30: (* 关 B；按 processMode 分支 *)
        valveARun := FALSE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        IF processMode THEN
            autoStep := 32;
        ELSE
            autoStep := 40;
        END_IF

    32: (* 开阀门 C *)
        valveCRun := TRUE;
        IF levelSensor >= 100 THEN
            valveCRun := FALSE;
            autoStep := 40;
        END_IF

    40: (* 启动搅拌电机 *)
        mixMotorRun := TRUE;
        IF NOT autoMixDone AND rtComplete.Q THEN
            autoMixDone := TRUE;
            mixMotorRun := FALSE;
            valveDRun := TRUE;
            autoStep := 50;
        END_IF

    50: (* 流程已完成：打开阀门 D 放料，自动流程结束 *)
        valveARun := FALSE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        mixMotorRun := FALSE;
        valveDRun := TRUE;
        autoStep := 0;

ELSE
    autoStep := 0;
END_CASE

END_FUNCTION_BLOCK
