# Multi-Pump Switching Control System

- **Difficulty:** Medium (medium)

## Requirements

In an industrial water supply system, there are 5 pumps, each of which can be controlled independently. The system needs to support both manual and automatic operating modes.
Based on the value of the mode variable, switch to the corresponding operating mode.
In manual mode, control the start and stop of the selected pump based on the value of pumpGroup[1..5].selection.
In automatic mode, compare the priority of each pump, and automatically select the 3 pumps with higher priority for water supply according to the method of three in use and two on standby.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `mode` | `BOOL` | FALSE: Manual mode<br>TRUE: Automatic mode |
| Input | `start` | `BOOL` | Start button, used to start the manually selected or automatically selected pump |
| Input | `stop` | `BOOL` | Stop button, used to stop all pumps |
| Input/Output | `pumpGroup` | `ARRAY[1..5] OF ST_Pump` | Five pump records passed by reference. Read priority and selection; write only RunComd. |

**Data type `ST_Pump`**

| Field | Data Type | Description |
| --- | --- | --- |
| `priority` | `INT` | Priority; larger values have higher priority. Read-only to the function block. |
| `selection` | `BOOL` | Manual-selection state. Read-only to the function block. |
| `RunComd` | `BOOL` | Run command written by the function block; TRUE runs and FALSE stops. |