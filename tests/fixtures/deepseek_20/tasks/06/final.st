(*
  公共题库第 06 题：Aeration Blower Delayed Start（曝气风机延时启动）
  接口严格按题面：
    输入 DO_LOW : BOOL
    输入 AERATION_E_STOP_NC : BOOL   (TRUE = 急停未动作/允许运行)
    输出 BLOWER_RUN : BOOL
    输出 AERATION_BLOWER_CYCLE_COUNT : UINT
  行为：
    1) DO_LOW 与 AERATION_E_STOP_NC 同时为 TRUE 并持续 5 s 后 BLOWER_RUN 置 TRUE；
    2) 任一条件失效（DO_LOW 变 FALSE 或急停动作）立即断开 BLOWER_RUN 并复位计时，
       新的需求必须重新等待完整 5 s；
    3) BLOWER_RUN 每个 FALSE->TRUE 上升沿使 AERATION_BLOWER_CYCLE_COUNT 加 1，
       连续运行期间不重复计数；
    4) 上电初始化（FB 实例初始化值）：BLOWER_RUN = FALSE，计数 = 0。
  说明：原题只给 BOOL 使能，不含转速斜坡。
*)
FUNCTION_BLOCK BlowerControl
VAR_INPUT
    DO_LOW              : BOOL;   (* TRUE: 溶解氧低，需要曝气 *)
    AERATION_E_STOP_NC  : BOOL;   (* TRUE: 急停未动作；FALSE: 急停动作 *)
END_VAR
VAR_OUTPUT
    BLOWER_RUN                  : BOOL;  (* 风机接触器运行命令 *)
    AERATION_BLOWER_CYCLE_COUNT : UINT;  (* 实际启动次数 *)
END_VAR
VAR
    (* 5 秒启动延时：以需求与安全条件的组合为基准源 *)
    fbDelayTimer   : TON;
    (* 上升沿检测辅助 *)
    rtBlowerRun    : R_TRIG;
    (* 内部状态 *)
    xEnableRequest : BOOL;   (* 需求与安全条件同时满足 *)
END_VAR
VAR CONSTANT
    T_START_DELAY : TIME := T#5s;   (* 启动延时 5 s *)
END_VAR

(* 1. 需求与安全条件同时满足；急停优先（条件不满足即视为无效需求） *)
xEnableRequest := DO_LOW AND AERATION_E_STOP_NC;

(* 2. 启动延时：条件失效时 TON 的 IN = FALSE，输出与计时立即复位 *)
fbDelayTimer(IN := xEnableRequest, PT := T_START_DELAY);

(* 3. 只有完整满足 5 s 才允许输出；急停/DO 失效立即断开 *)
BLOWER_RUN := fbDelayTimer.Q AND xEnableRequest;

(* 4. 仅在 BLOWER_RUN 的 FALSE->TRUE 上升沿计一次启动 *)
rtBlowerRun(CLK := BLOWER_RUN);
IF rtBlowerRun.Q THEN
    AERATION_BLOWER_CYCLE_COUNT := AERATION_BLOWER_CYCLE_COUNT + 1;
END_IF

END_FUNCTION_BLOCK
