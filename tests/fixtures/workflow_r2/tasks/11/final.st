(*
  公共题库第 11 题：Automated Production Line Control
  主功能块：Q11
  接口严格保持题面定义（全部 BOOL，方向不变）。
  题面未定义之处（见末尾说明）采取保守实现：
   - 手动 / 自动互锁：MotorForward 与 MotorReverse 永不同时为真。
   - 自动模式用状态机顺序推进 A -> B -> C。
   - 按钮按上升沿采样（"触发"语义），避免长按造成连续动作。
*)

TYPE Q11_STATE :
(
    Q11_IDLE        := 0,   (* 等待产品到达 A *)
    Q11_AT_A        := 10,  (* 产品已在 A，等待 ButtonA *)
    Q11_MOVE_AB     := 20,  (* 正转由 A 送往 B *)
    Q11_AT_B        := 30,  (* 产品已在 B，等待 ButtonB *)
    Q11_MOVE_BC     := 40,  (* 正转由 B 送往 C *)
    Q11_AT_C        := 50,  (* 产品已在 C，等待 ButtonC *)
    Q11_DONE        := 60   (* 加工完成，CompletionLight 点亮 *)
);
END_TYPE

FUNCTION_BLOCK Q11
VAR_INPUT
    Mode          : BOOL;   (* 0 = 手动, 1 = 自动 *)
    ForwardButton : BOOL;   (* 手动正转按钮 *)
    ReverseButton : BOOL;   (* 手动反转按钮 *)
    SensorA       : BOOL;   (* A 工位到位传感器 *)
    SensorB       : BOOL;   (* B 工位到位传感器 *)
    SensorC       : BOOL;   (* C 工位到位传感器 *)
    ButtonA       : BOOL;   (* A 工位加工完成按钮 *)
    ButtonB       : BOOL;   (* B 工位加工完成按钮 *)
    ButtonC       : BOOL;   (* C 工位加工完成按钮 *)
END_VAR
VAR_OUTPUT
    MotorForward    : BOOL; (* 电机正转 *)
    MotorReverse    : BOOL; (* 电机反转 *)
    CompletionLight : BOOL; (* 产品加工完成指示灯 *)
END_VAR
VAR
    State         : Q11_STATE := Q11_IDLE;
    PrevMode      : BOOL := FALSE;
    PrevForward   : BOOL := FALSE;
    PrevReverse   : BOOL := FALSE;
    PrevButtonA   : BOOL := FALSE;
    PrevButtonB   : BOOL := FALSE;
    PrevButtonC   : BOOL := FALSE;
    R_Forward     : BOOL := FALSE;  (* 按钮上升沿 *)
    R_Reverse     : BOOL := FALSE;
    R_ButtonA     : BOOL := FALSE;
    R_ButtonB     : BOOL := FALSE;
    R_ButtonC     : BOOL := FALSE;
END_VAR

(* ---------- 按钮上升沿 ---------- *)
R_Forward  := ForwardButton AND NOT PrevForward;
R_Reverse  := ReverseButton AND NOT PrevReverse;
R_ButtonA  := ButtonA AND NOT PrevButtonA;
R_ButtonB  := ButtonB AND NOT PrevButtonB;
R_ButtonC  := ButtonC AND NOT PrevButtonC;

(* ---------- 模式切换：进入自动模式时按当前位置重新对齐状态 ---------- *)
IF Mode <> PrevMode THEN
    IF Mode THEN
        (* 切换到自动：优先按传感器对齐；否则退回 IDLE *)
        IF SensorC THEN
            State := Q11_AT_C;
        ELSIF SensorB THEN
            State := Q11_AT_B;
        ELSIF SensorA THEN
            State := Q11_AT_A;
        ELSE
            State := Q11_IDLE;
        END_IF
        (* 若切换瞬间 C 工位已有产品且已完成，交给 DONE 分支处理 *)
        IF SensorC AND ButtonC AND NOT PrevButtonC THEN
            State := Q11_AT_C;
        END_IF
    ELSE
        State := Q11_IDLE;
    END_IF
END_IF

(* ---------- 缺省输出 ---------- *)
MotorForward    := FALSE;
MotorReverse    := FALSE;
CompletionLight := FALSE;

IF Mode THEN
    (* ================= 自动模式 ================= *)
    CASE State OF
    Q11_IDLE:
        IF SensorA THEN
            State := Q11_AT_A;
        END_IF

    Q11_AT_A:
        IF NOT SensorA THEN
            (* 产品未在 A（可能已被取走），回到等待 *)
            State := Q11_IDLE;
        ELSIF R_ButtonA THEN
            State := Q11_MOVE_AB;
        END_IF

    Q11_MOVE_AB:
        MotorForward := TRUE;
        IF SensorB THEN
            MotorForward := FALSE;
            State := Q11_AT_B;
        END_IF

    Q11_AT_B:
        IF R_ButtonB THEN
            State := Q11_MOVE_BC;
        END_IF

    Q11_MOVE_BC:
        MotorForward := TRUE;
        IF SensorC THEN
            MotorForward := FALSE;
            State := Q11_AT_C;
        END_IF

    Q11_AT_C:
        IF R_ButtonC THEN
            State := Q11_DONE;
        END_IF

    Q11_DONE:
        IF SensorC THEN
            CompletionLight := TRUE;
        ELSE
            (* 产品被取走：完成灯熄灭，回到初始 *)
            CompletionLight := FALSE;
            State := Q11_IDLE;
        END_IF

    ELSE
        State := Q11_IDLE;
    END_CASE
ELSE
    (* ================= 手动模式 ================= *)
    State := Q11_IDLE;
    (* 正反转互锁：同时按下时两者都不输出 *)
    IF R_Forward AND NOT ReverseButton THEN
        MotorForward := TRUE;
    ELSIF R_Reverse AND NOT ForwardButton THEN
        MotorReverse := TRUE;
    END_IF
END_IF

(* 最终安全互锁：两输出永不同时为真 *)
IF MotorForward AND MotorReverse THEN
    MotorForward := FALSE;
    MotorReverse := FALSE;
END_IF

(* ---------- 保存边沿历史 ---------- *)
PrevMode    := Mode;
PrevForward := ForwardButton;
PrevReverse := ReverseButton;
PrevButtonA := ButtonA;
PrevButtonB := ButtonB;
PrevButtonC := ButtonC;

END_FUNCTION_BLOCK
