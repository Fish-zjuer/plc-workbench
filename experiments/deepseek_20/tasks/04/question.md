# Jam Pump Debouncing and Runtime Maintenance

- **Difficulty:** Easy (easy)

## Requirements

Control a jam transfer pump on a food production line, including viscosity-signal debouncing, emergency-stop priority, runtime accumulation and a maintenance-due indication.

1. Accept the viscosity condition only after VISCOSITY_OK has remained TRUE for DebounceTime. Invalidate the condition immediately when the input becomes FALSE.
2. Allow VFD_RUN to be TRUE only when PASTE_E_STOP_NC is TRUE and the viscosity condition is valid. An emergency stop immediately disables the run output and clears any incomplete debounce timing.
3. Accumulate PUMP_RUNTIME_ACC using the actual invocation interval CycleTime only while VFD_RUN is TRUE. Preserve the accumulated time while the pump is stopped.
4. Set PUMP_MAINT_DUE when accumulated runtime reaches 500 hours. This indication is informational and must not affect pump operation or the safety permissive.
5. At power-up, initialize the run output to OFF, accumulated runtime to zero and the maintenance indication to FALSE.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `VISCOSITY_OK` | `BOOL` | Raw signal indicating that viscosity is within the permitted range. |
| Input | `PASTE_E_STOP_NC` | `BOOL` | Normally closed emergency-stop circuit; TRUE permits operation and FALSE means emergency stop. |
| Input | `DebounceTime` | `TIME` | Required continuous valid duration for the viscosity signal; must be positive. |
| Input | `CycleTime` | `TIME` | Actual elapsed interval represented by this invocation; must be positive. |
| Output | `VFD_RUN` | `BOOL` | Pump variable-frequency-drive run command. |
| Output | `PUMP_MAINT_DUE` | `BOOL` | Maintenance indication when accumulated runtime reaches 500 hours. |
| Output | `PUMP_RUNTIME_ACC` | `LTIME` | Accumulated enabled runtime, using a long-duration time type. |