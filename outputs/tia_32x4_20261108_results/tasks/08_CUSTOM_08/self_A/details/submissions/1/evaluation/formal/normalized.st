FUNCTION_BLOCK FB_CraneSpeedCheck

   VAR_INPUT 
      LeftSpeed10 : INT;
      RightSpeed10 : INT;
      ReferenceSpeed10 : INT;
   END_VAR
   VAR_OUTPUT 
      SyncOK : BOOL;
      SyncBad : BOOL;
      Invalid : BOOL;
   END_VAR
   VAR 
      tmpValid : BOOL;
      tmpLeft : DINT;
      tmpRight : DINT;
      tmpRef : DINT;
      tmpDiff12 : DINT;
      tmpSumRatio : DINT;
      tmpRatioTarget : DINT;
      tmpSyncCond : BOOL;
      tmpRatioCond : BOOL;
   END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : DINT;
WBTEMP_2 : DINT;
WBTEMP_3 : DINT;
WBTEMP_4 : DINT;
WBTEMP_5 : DINT;
WBTEMP_6 : DINT;
WBTEMP_7 : BOOL;
WBTEMP_8 : BOOL;
END_VAR

     
tmpValid := WBTEMP_0;
tmpLeft := WBTEMP_1;
tmpRight := WBTEMP_2;
tmpRef := WBTEMP_3;
tmpDiff12 := WBTEMP_4;
tmpSumRatio := WBTEMP_5;
tmpRatioTarget := WBTEMP_6;
tmpSyncCond := WBTEMP_7;
tmpRatioCond := WBTEMP_8;

      // 每周期先复位所有输出，保证恰好一个为 TRUE
      SyncOK := FALSE;
      SyncBad := FALSE;
      Invalid := FALSE;

      // 拓宽为 DINT 后再进行后续运算，避免 INT 溢出
      tmpLeft := INT_TO_DINT(LeftSpeed10);
      tmpRight := INT_TO_DINT(RightSpeed10);
      tmpRef := INT_TO_DINT(ReferenceSpeed10);

      // 量程校验：三路均在 0..100，且参考速度 > 0
      tmpValid := (tmpLeft >= 0) AND (tmpLeft <= 100)
                   AND (tmpRight >= 0) AND (tmpRight <= 100)
                   AND (tmpRef > 0) AND (tmpRef <= 100);

      IF NOT tmpValid THEN
         Invalid := TRUE;
      ELSE
         // 同步约束：|L - R| <= 1
         tmpDiff12 := tmpLeft - tmpRight;
         IF tmpDiff12 < 0 THEN
            tmpDiff12 := -tmpDiff12;
         END_IF;
         tmpSyncCond := (tmpDiff12 <= 1);

         // 传动比约束：|L + R - 13 * Ref| <= 2
         tmpRatioTarget := 13 * tmpRef;
         tmpSumRatio := tmpLeft + tmpRight - tmpRatioTarget;
         IF tmpSumRatio < 0 THEN
            tmpSumRatio := -tmpSumRatio;
         END_IF;
         tmpRatioCond := (tmpSumRatio <= 2);

         IF tmpSyncCond AND tmpRatioCond THEN
            SyncOK := TRUE;
         ELSE
            SyncBad := TRUE;
         END_IF;
      END_IF;

END_FUNCTION_BLOCK