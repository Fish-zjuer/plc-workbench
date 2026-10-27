(*
    Q19  Mechanical Arm Control
    原始接口全部保留（名称/类型/方向）。无 ARRAY[*] / VARIANT 参数。
    题面未定义的细节（见文件末尾注释）按工程常识实现。
*)

TYPE Q19_STATE :
(
    ST_IDLE := 0,      (* 等待启动 *)
    ST_DOWN1,          (* 下移到下限位 *)
    ST_GRIP,           (* 夹紧完成 *)
    ST_UP1,            (* 上移到上限位 *)
    ST_RIGHT,          (* 右移到右限位 *)
    ST_DOWN2,          (* 下移到下限位 *)
    ST_RELEASE,        (* 松开完成 *)
    ST_UP2,            (* 上移到上限位 *)
    ST_LEFT,           (* 左移到左限位，循环结束 *)
    ST_DONE            (* 单步/单循环：序列完成 *)
);
END_TYPE

FUNCTION_BLOCK Q19
VAR_INPUT
    ManualMode          : BOOL;
    SingleStepMode      : BOOL;
    SingleCycleMode     : BOOL;
    ContinuousMode      : BOOL;
    EmergencyStop       : BOOL;   (* FALSE: 急停触发  TRUE: 无急停 *)
    Start               : BOOL;
    DownButton          : BOOL;
    UpButton            : BOOL;
    LeftButton          : BOOL;
    RightButton         : BOOL;
    GripButton          : BOOL;
    ReleaseButton       : BOOL;
    DownLimitSwitch     : BOOL;
    UpLimitSwitch       : BOOL;
    LeftLimitSwitch     : BOOL;
    RightLimitSwitch    : BOOL;
    GripLimitSwitch     : BOOL;
    ReleaseLimitSwitch  : BOOL;
END_VAR
VAR_OUTPUT
    MoveDown            : BOOL;
    MoveUp              : BOOL;
    MoveLeft            : BOOL;
    MoveRight           : BOOL;
    ActivateGrip        : BOOL;
    ActivateRelease     : BOOL;
END_VAR
VAR
    state               : Q19_STATE := Q19_STATE#ST_IDLE;
    rtStart             : R_TRIG;   (* 启动按钮上升沿 *)
    edgeStart           : BOOL;
    armed               : BOOL;     (* 单步：当前动作已放行 *)
    prevModeManual      : BOOL;
END_VAR

(* ---------- 启动上升沿 ---------- *)
rtStart(CLK := Start);
edgeStart := rtStart.Q;

(* ---------- 模式切换清除状态 ---------- *)
IF ManualMode <> prevModeManual THEN
    prevModeManual := ManualMode;
    IF ManualMode THEN
        state := Q19_STATE#ST_IDLE;
        armed := FALSE;
    END_IF;
END_IF

(* ---------- 输出复位 ---------- *)
MoveDown        := FALSE;
MoveUp          := FALSE;
MoveLeft        := FALSE;
MoveRight       := FALSE;
ActivateGrip    := FALSE;
ActivateRelease := FALSE;

(* ---------- 急停：立即停止所有动作 ---------- *)
IF NOT EmergencyStop THEN
    state := Q19_STATE#ST_IDLE;
    armed := FALSE;
    RETURN;
END_IF

(* ================= 手动模式 ================= *)
IF ManualMode THEN
    armed := FALSE;
    state := Q19_STATE#ST_IDLE;

    IF DownButton AND NOT DownLimitSwitch THEN
        MoveDown := TRUE;
    END_IF;
    IF UpButton AND NOT UpLimitSwitch THEN
        MoveUp := TRUE;
    END_IF;
    IF LeftButton AND NOT LeftLimitSwitch THEN
        MoveLeft := TRUE;
    END_IF;
    IF RightButton AND NOT RightLimitSwitch THEN
        MoveRight := TRUE;
    END_IF;
    IF GripButton AND NOT GripLimitSwitch THEN
        ActivateGrip := TRUE;
    END_IF;
    IF ReleaseButton AND NOT ReleaseLimitSwitch THEN
        ActivateRelease := TRUE;
    END_IF;
    RETURN;
END_IF

(* ================= 自动模式（单步 / 单循环 / 连续） ================= *)
IF SingleStepMode THEN
    (* 每个上升沿放行一个动作 *)
    IF edgeStart THEN
        armed := NOT armed;
    END_IF;
ELSIF state = Q19_STATE#ST_IDLE AND edgeStart THEN
    (* 单循环 / 连续：按下启动开始 */
    armed := TRUE;
END_IF

(* 序列完成后：连续模式自动重新开始，其他模式等待启动 *)
IF state = Q19_STATE#ST_DONE THEN
    IF ContinuousMode THEN
        state := Q19_STATE#ST_DOWN1;
    ELSE
        state := Q19_STATE#ST_IDLE;
        armed := FALSE;
    END_IF;
END_IF

(* 单步模式下新动作尚未放行则保持等待，不改状态 *)
IF SingleStepMode THEN
    IF NOT armed THEN
        RETURN;
    END_IF
END_IF

CASE state OF
Q19_STATE#ST_IDLE:
    IF SingleCycleMode OR ContinuousMode THEN
        IF edgeStart THEN
            armed := TRUE;
        END_IF
    END_IF
    IF armed THEN
        state := Q19_STATE#ST_DOWN1;
    END_IF

Q19_STATE#ST_DOWN1:
    MoveDown := TRUE;
    IF DownLimitSwitch THEN
        state := Q19_STATE#ST_GRIP;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

Q19_STATE#ST_GRIP:
    ActivateGrip := TRUE;
    IF GripLimitSwitch THEN
        state := Q19_STATE#ST_UP1;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

Q19_STATE#ST_UP1:
    MoveUp := TRUE;
    IF UpLimitSwitch THEN
        state := Q19_STATE#ST_RIGHT;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

Q19_STATE#ST_RIGHT:
    MoveRight := TRUE;
    IF RightLimitSwitch THEN
        state := Q19_STATE#ST_DOWN2;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

Q19_STATE#ST_DOWN2:
    MoveDown := TRUE;
    IF DownLimitSwitch THEN
        state := Q19_STATE#ST_RELEASE;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

Q19_STATE#ST_RELEASE:
    ActivateRelease := TRUE;
    IF ReleaseLimitSwitch THEN
        state := Q19_STATE#ST_UP2;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

Q19_STATE#ST_UP2:
    MoveUp := TRUE;
    IF UpLimitSwitch THEN
        state := Q19_STATE#ST_LEFT;
        IF SingleStepMode THEN
            armed := FALSE;
        END_IF
    END_IF

Q19_STATE#ST_LEFT:
    MoveLeft := TRUE;
    IF LeftLimitSwitch THEN
        IF SingleStepMode THEN
            state := Q19_STATE#ST_IDLE;
        ELSE
            state := Q19_STATE#ST_DONE;
        END_IF
        armed := FALSE;
    END_IF

Q19_STATE#ST_DONE:
    ;

ELSE
    state := Q19_STATE#ST_IDLE;
END_CASE

(*
  题面未定义、此处采用的工程约定：
  1. 自动序列只要闭环一个完整周期（8 个动作），单步模式在 ST_LEFT 完成后回到 ST_IDLE，
     下一次启动即重新从 MoveDown 开始。
  2. 单步模式下“确认”用 Start 的上升沿；一个周期内逐次放行，未放行时动作保持。
  3. 单循环/连续模式：Start 必须在 ST_IDLE 时的上升沿才启动；运行中 Start 不打断。
  4. 急停（EmergencyStop=FALSE）立即清除全部输出并使序列回到 ST_IDLE，恢复后需重新启动。
  5. 手动模式下抓/放动作以 GripLimitSwitch / ReleaseLimitSwitch 为到位反馈，
     到位即停止输出（按住按钮也不动作）。
  6. 手动运行时若按下某方向按钮且该方向限位已为 TRUE，则不输出该方向命令。
  7. 位置按钮与限位互不冲突时允许同时输出（如上下同时按下，题面未禁止组合）。
  8. 模式输入互斥由调用方保证；若同时为 FALSE，仅急停判定，无动作输出。
*)
