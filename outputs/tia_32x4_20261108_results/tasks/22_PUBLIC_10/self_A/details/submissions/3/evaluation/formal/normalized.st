FUNCTION_BLOCK Q10

   VAR_INPUT
      TemperatureSensorInput : REAL;
      SetTemperature : REAL;
   END_VAR
   VAR_OUTPUT
      CurrentTemperature : REAL;
      SetTempDisplay : REAL;
      HeaterStatus : BOOL;
      OverheatProtection : BOOL;
      HeaterOutput : BOOL;
   END_VAR
   VAR
      heaterTimer : TON;
      coolTimer : TON;
      protectionLatched : BOOL;
      heatDemand : BOOL;
      sensorFault : BOOL;
      protectionReleased : BOOL;
   END_VAR

     
   // 温度显示
   CurrentTemperature := TemperatureSensorInput;
   SetTempDisplay := SetTemperature;

   // 传感器故障判断：小于0或大于100视为故障
   sensorFault := (TemperatureSensorInput < 0.0) OR (TemperatureSensorInput > 100.0);

   // 有效传感器时判断加热需求
   heatDemand := (NOT sensorFault) AND (TemperatureSensorInput < SetTemperature);

   // 默认加热输出关闭
   HeaterOutput := FALSE;
   protectionReleased := FALSE;

   IF sensorFault THEN
      // 传感器故障：关闭加热，清除连续加热计时与冷却计时
      heaterTimer(IN := FALSE, PT := T#5s);
      coolTimer(IN := FALSE, PT := T#3s);
      protectionLatched := FALSE;
   ELSE
      // 保护中的冷却计时处理
      IF protectionLatched THEN
         heaterTimer(IN := FALSE, PT := T#5s);
         coolTimer(IN := TRUE, PT := T#3s);
         IF coolTimer.Q THEN
            protectionLatched := FALSE;
            protectionReleased := TRUE;
            coolTimer(IN := FALSE, PT := T#3s);
         END_IF;
      ELSE
         // 未保护：清除冷却计时
         coolTimer(IN := FALSE, PT := T#3s);
      END_IF;

      IF NOT protectionLatched THEN
         // 无保护（含刚解除保护）：根据需求控制加热
         HeaterOutput := heatDemand;
         heaterTimer(IN := HeaterOutput, PT := T#5s);
         IF heaterTimer.Q THEN
            // 连续加热超过 5s：触发过热保护并关闭加热
            protectionLatched := TRUE;
            protectionReleased := FALSE;
            HeaterOutput := FALSE;
            heaterTimer(IN := FALSE, PT := T#5s);
            coolTimer(IN := TRUE, PT := T#3s);
         END_IF;
      END_IF;
   END_IF;

   // 状态输出
   OverheatProtection := protectionLatched;
   HeaterStatus := HeaterOutput;
END_FUNCTION_BLOCK