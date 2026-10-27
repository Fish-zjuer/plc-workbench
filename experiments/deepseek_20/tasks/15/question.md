# Material Proportioning Process Control

- **Difficulty:** Hard (hard)

## Requirements

Design a PLC program to control a material proportioning process that requires mixing three types of materials according to specific requirements and then delivering them to the next process through valve D. The system needs to support both manual and automatic operation modes and be able to safely stop all equipment when an emergency stop signal is triggered.
Control requirements:
Emergency Stop Logic: The estop(=FALSE) signal is used for emergency stopping of all equipment.
Manual Mode: opeMode=false, manually control the start/stop of valves A, B, C, D, and the mixing motor.
Automatic Mode: opeMode=true, equipment operates automatically according to the process flow.
Implement the emergency stop logic to ensure that all equipment stops immediately when the emergency stop signal is triggered.
In manual mode, manually control the start/stop of valves and the mixing motor.
For example, pressing the valve A start button valveAStart (triggering a rising edge) causes valve A to run (valveARun=TRUE); pressing the valve A start button valveAStart again (triggering a rising edge) stops valve A (valveARun=FALSE).
In automatic mode, implement the following control logic based on the process flow:
Press the autoStart button to start the automatic process, first opening valve A.
When the liquid level sensor levelSensor reaches 50cm, close valve A and open valve B.
When the liquid level sensor reaches 80cm, close valve B.
Based on processMode:
If processMode=false, start the mixing motor; after receiving the mixing complete signal, stop the mixing motor, open valve D, and the automatic process ends.
If processMode=true, open valve C; when the liquid level sensor reaches 100cm, close valve C, start the mixing motor; after receiving the mixing complete signal, stop the mixing motor, open valve D, and the automatic process ends.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `estop` | `BOOL` | Emergency Stop Signal<br>FALSE: Emergency stop triggered<br>TRUE: No emergency stop triggered |
| Input | `opeMode` | `BOOL` | Operation Mode<br>FALSE: Manual Operation Mode<br>TRUE: Automatic Operation Mode |
| Input | `valveAStart` | `BOOL` | Valve A Start Button |
| Input | `valveBStart` | `BOOL` | Valve B Start Button |
| Input | `valveCStart` | `BOOL` | Valve C Start Button |
| Input | `valveDStart` | `BOOL` | Valve D Start Button |
| Input | `mixMotorStart` | `BOOL` | Mixing Motor Start Button |
| Input | `autoStart` | `BOOL` | Automatic Start Button |
| Input | `processMode` | `BOOL` | Process Mode |
| Input | `levelSensor` | `INT` | Liquid Level Sensor (unit cm) |
| Input | `mixMotorComplete` | `BOOL` | Mixing Complete Signal |
| Output | `valveARun` | `BOOL` | Valve A Run Command |
| Output | `valveBRun` | `BOOL` | Valve B Run Command |
| Output | `valveCRun` | `BOOL` | Valve C Run Command |
| Output | `valveDRun` | `BOOL` | Valve D Run Command |
| Output | `mixMotorRun` | `BOOL` | Mixing Motor Run Command |