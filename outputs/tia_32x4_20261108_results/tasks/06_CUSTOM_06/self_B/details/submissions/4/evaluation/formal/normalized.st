FUNCTION_BLOCK FB_CompressorPressure

  VAR_INPUT
    Enable : BOOL;
    Reset : BOOL;
    PressureKpa : LREAL;
    AirUseFlow : LREAL;
    Kp : LREAL;
    Ki : LREAL;
    DtSec : LREAL;
  END_VAR

  VAR_OUTPUT
    CapacityPct : LREAL;
    Integral : LREAL;
    Saturated : BOOL;
    Error : BOOL;
  END_VAR

  VAR
    e : LREAL;
    FF : LREAL;
    Ic_candidate : LREAL;
    Uc_candidate : LREAL;
    U_final : LREAL;
    valid_inputs : BOOL;
    reject_integration : BOOL;
  END_VAR
VAR_INPUT
WBTEMP_0 : LREAL;
WBTEMP_1 : LREAL;
WBTEMP_2 : LREAL;
WBTEMP_3 : LREAL;
WBTEMP_4 : LREAL;
WBTEMP_5 : BOOL;
WBTEMP_6 : BOOL;
END_VAR


     
e := WBTEMP_0;
FF := WBTEMP_1;
Ic_candidate := WBTEMP_2;
Uc_candidate := WBTEMP_3;
U_final := WBTEMP_4;
valid_inputs := WBTEMP_5;
reject_integration := WBTEMP_6;
    // Initialize Integral to 0 on first scan or if not managed by static VAR (here it is output, so we ensure start value)
    // Note: In Siemens FB, outputs are retained between calls unless reset. 
    // The requirement says "Initially Integral=0". We assume the caller handles power-on reset or we rely on default 0.0 for LREAL.
    // However, to be safe against uninitialized memory in some contexts, we can explicitly check if it's the very first call? 
    // No, standard behavior is 0.0 initialization. The warning was likely due to reading before writing in some paths. 
    // Let's ensure all paths write to Integral or preserve it correctly.

    // Check validity of inputs (Range checks)
    valid_inputs := FALSE;
    
    IF (PressureKpa >= 0.0 AND PressureKpa <= 1000.0) THEN
        IF (AirUseFlow >= 0.0 AND AirUseFlow <= 90.0) THEN
            IF (Kp >= 0.0 AND Kp <= 1.0) THEN
                IF (Ki >= 0.0 AND Ki <= 0.1) THEN
                    IF (DtSec >= 0.001 AND DtSec <= 1.0) THEN
                        valid_inputs := TRUE;
                    END_IF;
                END_IF;
            END_IF;
        END_IF;
    END_IF;

    // Priority 1: Reset
    IF Reset THEN
        Integral := 0.0;
        CapacityPct := 0.0;
        Saturated := FALSE;
        Error := FALSE;
    ELSE
        // Priority 2: Disable
        IF NOT Enable THEN
            // Preserve Integral (do nothing to #Integral)
            CapacityPct := 0.0;
            Saturated := FALSE;
            Error := FALSE;
        ELSE
            // Priority 3: Invalid Inputs while Enabled
            IF NOT valid_inputs THEN
                // Preserve Integral (do nothing to #Integral)
                CapacityPct := 0.0;
                Saturated := FALSE;
                Error := TRUE;
            ELSE
                // Legal Enabled Call
                Error := FALSE;

                // Calculate Error term
                e := 500.0 - PressureKpa;

                // Calculate Feedforward
                FF := 2.0 * AirUseFlow;

                // Candidate Integration Step
                Ic_candidate := Integral + (Ki * e * DtSec);

                // Candidate Unclamped Output
                Uc_candidate := FF + (Kp * e) + Ic_candidate;

                // Anti-Windup Logic
                // Reject integration step when:
                // (Uc > 100 AND e > 0) OR (Uc < 0 AND e < 0)
                reject_integration := FALSE;
                
                IF (Uc_candidate > 100.0 AND e > 0.0) THEN
                    reject_integration := TRUE;
                ELSIF (Uc_candidate < 0.0 AND e < 0.0) THEN
                    reject_integration := TRUE;
                END_IF;

                // Determine Final Integral State
                IF reject_integration THEN
                    // Preserve previous integral: Explicitly keep current value (no-op needed, but structure requires statement)
                    // In SCL, an empty block is invalid. We assign it to itself or just let it fall through if we didn't change it.
                    // Since we haven't changed #Integral yet in this branch, it remains preserved.
                    ; // Empty statement allowed in IF/ELSE blocks in TIA Portal V21? Actually, strict syntax often dislikes bare semicolons in complex nesting without context.
                    // Safer approach: Only update if NOT rejected.
                ELSE
                    // Accept candidate integral
                    Integral := Ic_candidate;
                END_IF;

                // Recompute U using final integral
                U_final := FF + (Kp * e) + Integral;

                // Set CapacityPct = LIMIT(0, U, 100)
                IF U_final < 0.0 THEN
                    CapacityPct := 0.0;
                ELSIF U_final > 100.0 THEN
                    CapacityPct := 100.0;
                ELSE
                    CapacityPct := U_final;
                END_IF;

                // Set Saturated Flag
                // TRUE only when U is strictly below 0 or above 100
                IF (U_final < 0.0 OR U_final > 100.0) THEN
                    Saturated := TRUE;
                ELSE
                    Saturated := FALSE;
                END_IF;
            END_IF;
        END_IF;
    END_IF;

END_FUNCTION_BLOCK