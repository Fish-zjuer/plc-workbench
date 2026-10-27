# Aeration Blower Delayed Start

- **Difficulty:** Easy (easy)

## Requirements

Control a wastewater-treatment aeration blower with a low-dissolved-oxygen demand, a 5-second start delay, emergency-stop priority and start-cycle counting.

1. Start delay timing when both DO_LOW and AERATION_E_STOP_NC are TRUE. Allow BLOWER_RUN to become TRUE only after these conditions have remained satisfied for 5 seconds.
2. If DO_LOW becomes FALSE or an emergency stop occurs, immediately disable BLOWER_RUN and reset the start timer, whether timing is incomplete or complete. A new demand must wait the full 5 seconds again.
3. Increment AERATION_BLOWER_CYCLE_COUNT once on each FALSE-to-TRUE transition of BLOWER_RUN. Do not count repeatedly during continuous operation.
4. At power-up, initialize the blower to OFF and the start count to zero. The start delay gates a BOOL enable; no continuous speed ramp is required.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `DO_LOW` | `BOOL` | Dissolved oxygen is below its threshold and aeration is needed. |
| Input | `AERATION_E_STOP_NC` | `BOOL` | TRUE means the emergency stop is inactive; FALSE means it is active. |
| Output | `BLOWER_RUN` | `BOOL` | Blower motor-contactor run command. |
| Output | `AERATION_BLOWER_CYCLE_COUNT` | `UINT` | Count of actual blower starts. |