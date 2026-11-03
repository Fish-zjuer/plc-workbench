(*
  Q15 - Material Proportioning Process Control
  原题接口与原方向、类型完全保留；本题只用到 BOOL/INT，
  题面无 ARRAY[*]、无 VARIANT，无需桥接。
  题面未定义、由本实现裁决的细节：
    - 自动流程为内部步序状态机；autoStart 取上升沿启动（空闲步时）。
    - 液位判定采用 >=，并按题目“到 50 关 A 开 B”的同一扫描完成阀门切换；
      同理 80 关 B 与开 C 在同一扫描完成，使后续扫描可见 C 运行。
    - 到达 100cm 的同一扫描关 C 并启动搅拌电机。
    - 收到 mixMotorComplete 上升沿后停搅拌、开阀门 D，自动流程结束（回空闲）。
    - 自动流程结束后再按 autoStart 上升沿可重新开始。
    - 手动模式 5 个按钮均为上升沿翻转；切到自动或急停会清除手动保持量。
    - 急停(estop=FALSE) 最高优先级：输出全部清零并复位自动步序。
*)

FUNCTION_BLOCK Q15
VAR_INPUT
    estop            : BOOL;   (* FALSE: 急停触发 *)
    opeMode          : BOOL;   (* FALSE: 手动, TRUE: 自动 *)
    valveAStart      : BOOL;
    valveBStart      : BOOL;
    valveCStart      : BOOL;
    valveDStart      : BOOL;
    mixMotorStart    : BOOL;
    autoStart        : BOOL;
    processMode      : BOOL;
    levelSensor      : INT;    (* 液位 cm *)
    mixMotorComplete : BOOL;
END_VAR
VAR_OUTPUT
    valveARun        : BOOL;
    valveBRun        : BOOL;
    valveCRun        : BOOL;
    valveDRun        : BOOL;
    mixMotorRun      : BOOL;
END_VAR
VAR
    (* 手动按钮上升沿 *)
    rtA              : R_TRIG;
    rtB              : R_TRIG;
    rtC              : R_TRIG;
    rtD              : R_TRIG;
    rtMix            : R_TRIG;
    (* 手动输出保持 *)
    manA             : BOOL;
    manB             : BOOL;
    manC             : BOOL;
    manD             : BOOL;
    manMix           : BOOL;
    (* 自动流程 *)
    rtAuto           : R_TRIG;
    rtComplete       : R_TRIG;
    autoStep         : INT;    (* 0 空闲 *)
END_VAR

(* ---- 边沿检测 ---- *)
rtA(CLK := valveAStart);
rtB(CLK := valveBStart);
rtC(CLK := valveCStart);
rtD(CLK := valveDStart);
rtMix(CLK := mixMotorStart);
rtAuto(CLK := autoStart);
rtComplete(CLK := mixMotorComplete);

(* ---- 急停：最高优先级 ---- *)
IF NOT estop THEN
    manA := FALSE;
    manB := FALSE;
    manC := FALSE;
    manD := FALSE;
    manMix := FALSE;
    autoStep := 0;
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
(* 自动模式下忽略手动保持量 *)
manA := FALSE;
manB := FALSE;
manC := FALSE;
manD := FALSE;
manMix := FALSE;

(* 启动 / 重启自动流程 *)
IF autoStep = 0 AND rtAuto.Q THEN
    autoStep := 10;
END_IF

CASE autoStep OF
    0:  (* 空闲：保持上一次结束状态，由 autoStart 重新启动 *)
        ;

    10: (* 开阀门 A 进料 *)
        valveARun := TRUE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        IF levelSensor >= 50 THEN
            (* 同一扫描完成“关 A 开 B” *)
            valveARun := FALSE;
            valveBRun := TRUE;
            autoStep := 20;
        END_IF

    20: (* 阀门 B 进料，到 80cm 关 B *)
        valveARun := FALSE;
        valveBRun := TRUE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        IF levelSensor >= 80 THEN
            valveBRun := FALSE;
            autoStep := 30;
        END_IF

    30: (* 关闭 B 后按 processMode 分支 *)
        valveARun := FALSE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        IF processMode THEN
            (* 同一扫描进入阀门 C 步，保证 B 关闭与 C 开启连续 *)
            autoStep := 32;
        ELSE
            autoStep := 40;
        END_IF

    32: (* 开阀门 C，到 100cm 关 C 并启动搅拌电机 *)
        valveARun := FALSE;
        valveBRun := FALSE;
        valveCRun := TRUE;
        valveDRun := FALSE;
        mixMotorRun := FALSE;
        IF levelSensor >= 100 THEN
            valveCRun := FALSE;
            mixMotorRun := TRUE;
            autoStep := 40;
        END_IF

    40: (* 搅拌进行中，等待混合完成信号 *)
        valveARun := FALSE;
        valveBRun := FALSE;
        valveCRun := FALSE;
        valveDRun := FALSE;
        mixMotorRun := TRUE;
        IF rtComplete.Q THEN
            mixMotorRun := FALSE;
            valveDRun := TRUE;
            autoStep := 0;      (* 自动流程结束 *)
        END_IF

ELSE
    autoStep := 0;
END_CASE

END_FUNCTION_BLOCK
