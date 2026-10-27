(* =====================================================================
   Q13 - Office HVAC Multi-mode Energy-Saving Control
   30 秒启动延时 + 按模式/节能选择生成温度设定点调整量
   接口严格保持原题名称、类型与方向。
   ===================================================================== *)

FUNCTION_BLOCK Q13
VAR_INPUT
    OCCUPANCY_DETECTED   : BOOL;   (* 占用检测（来自 CO2 传感器） *)
    ENERGY_SAVING_MODE   : BOOL;   (* TRUE=节能，FALSE=标准；仅在 Auto 模式生效 *)
    HVAC_MODE_SELECTOR   : INT;    (* 0 Auto, 1 Comfort, 2 Economy, 3 Night *)
END_VAR
VAR_OUTPUT
    SUPPLY_FAN_RUN       : BOOL;   (* 送风机运行允许 *)
    TEMP_SETPOINT_ADJUST : INT;    (* 温度设定点调整，单位 °C *)
END_VAR
VAR
    fbStartDelay         : TON;    (* 启动延时 30 s *)
    tonDelay             : TON;
    rtDelayStart         : R_TRIG;
    xFirstScan           : BOOL := TRUE;
    xDelayEnabled        : BOOL;   (* 允许计时的条件：占用且非 Night *)
    xNight               : BOOL;
    iAdjust              : INT;
END_VAR

(* ---------- 上电初始化 / 首次正常计算 ---------- *)
IF xFirstScan THEN
    xFirstScan := FALSE;
    SUPPLY_FAN_RUN       := FALSE;
    TEMP_SETPOINT_ADJUST := 0;
    rtDelayStart(CLK := FALSE);
    tonDelay(IN := FALSE, PT := T#30S);
    tonDelay(IN := FALSE, PT := T#30S);
END_IF

(* ---------- 模式译码：只有 3 为 Night ---------- *)
xNight := (HVAC_MODE_SELECTOR = 3);

(* ---------- 延时条件：占用且非 Night ---------- *)
xDelayEnabled := OCCUPANCY_DETECTED AND NOT xNight;

(* ---------- 30 s 启动延时（TON 内在逻辑：条件丢失即复位并重新计时） ---------- *)
fbStartDelay(IN := xDelayEnabled, PT := T#30S);
SUPPLY_FAN_RUN := xDelayEnabled AND fbStartDelay.Q;

(* ---------- 温度设定点调整 ---------- *)
IF xNight THEN
    (* 5. Night：无论占用均为 +4 *)
    iAdjust := 4;
ELSIF HVAC_MODE_SELECTOR = 1 THEN
    (* 4. Comfort：占用 0，不占用 +1 *)
    IF OCCUPANCY_DETECTED THEN
        iAdjust := 0;
    ELSE
        iAdjust := 1;
    END_IF
ELSIF HVAC_MODE_SELECTOR = 2 THEN
    (* 4. Economy：占用 0，不占用 +4 *)
    IF OCCUPANCY_DETECTED THEN
        iAdjust := 0;
    ELSE
        iAdjust := 4;
    END_IF
ELSE
    (* 3. Auto：占用 0；不占用时节能 +3，标准 +2 *)
    IF OCCUPANCY_DETECTED THEN
        iAdjust := 0;
    ELSIF ENERGY_SAVING_MODE THEN
        iAdjust := 3;
    ELSE
        iAdjust := 2;
    END_IF
END_IF

(* ---------- 6. 限幅 ±4 °C ---------- *)
IF iAdjust > 4 THEN
    iAdjust := 4;
ELSIF iAdjust < -4 THEN
    iAdjust := -4;
END_IF

TEMP_SETPOINT_ADJUST := iAdjust;
