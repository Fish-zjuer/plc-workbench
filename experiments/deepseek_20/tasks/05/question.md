# Weld Gap Alarm and Startup Inhibition

- **Difficulty:** Easy (easy)

## Requirements

Control a weld-gap alarm with power-up monitoring inhibition, input debouncing during normal monitoring and emergency-stop priority.

1. Gap_Exceeded indicates that the scanner has detected a weld gap exceeding the permitted 1.5 mm value.
2. Begin with a 5-second initialization inhibition period after power-up. During this period, Operator_Alert is FALSE, Weld_Soft_Start_Active is TRUE, and gap-signal debounce time does not accumulate.
3. Resume gap monitoring after initialization. Allow the alarm only after Gap_Exceeded has remained TRUE for DebounceTime. When the signal becomes FALSE, switch off the alarm and clear debounce timing.
4. When Weld_E_Stop_NC is FALSE, the emergency stop takes priority over initialization and normal monitoring. Operator_Alert must immediately become FALSE and any incomplete debounce timing must be cleared.
5. Weld_Soft_Start_Active indicates only the power-up inhibition period; it does not represent a continuous speed ramp.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `Gap_Exceeded` | `BOOL` | Scanner indication that the gap exceeds 1.5 mm. |
| Input | `Weld_E_Stop_NC` | `BOOL` | TRUE means the emergency stop is inactive; FALSE means it is active. |
| Input | `DebounceTime` | `TIME` | Gap-signal debounce duration during normal monitoring; must be positive. |
| Output | `Operator_Alert` | `BOOL` | Audible and visual alarm command. |
| Output | `Weld_Soft_Start_Active` | `BOOL` | Monitoring-inhibition status during the 5-second power-up initialization. |