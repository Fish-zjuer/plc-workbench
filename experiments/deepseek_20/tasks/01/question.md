# Automated Filling Line Control

- **Difficulty:** Easy (easy)

## Requirements

An automated filling line responsible for cleaning, filling, capping, and packaging bottles. Each step of the production line is controlled by PLC and triggered by signals from sensors and operators.
Control requirements:
When the sensor bottleSensor detects a bottle, it triggers the start of the cleaning pump and continues to work.
After cleaning is completed, the operator operates the button cleaningConfirmButton to trigger the cleaning completion signal, automatically starting the filling valve for filling.
After filling is completed, the operator operates the button fillingConfirmButton to trigger the filling completion signal, automatically starting the capping machine for capping.
After capping is completed, the operator operates the button cappingConfirmButton to trigger the capping completion signal, starting the packing machine for packaging.
After packaging is completed, the operator operates the button packingConfirmButton to trigger the packaging completion signal, lighting up the packaging completion indicator light.
After the operator picks up the packaged bottle, they press the confirmation button finishedButton to reset the indicator light and prepare for the next bottle's production cycle.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `bottleSensor` | `BOOL` | The bottle reaches the sensor, triggering a signal when a bottle is detected |
| Input | `cleaningConfirmButton` | `BOOL` | Operator confirmation button, used to confirm the completion of the cleaning process |
| Input | `fillingConfirmButton` | `BOOL` | Operator confirmation button, used to confirm the completion of the filling process |
| Input | `cappingConfirmButton` | `BOOL` | Operator confirmation button, used to confirm the completion of the capping process |
| Input | `packingConfirmButton` | `BOOL` | Operator confirmation button, used to confirm the completion of the packaging process |
| Input | `finishedButton` | `BOOL` | Operator confirmation button, used to confirm that the bottle has been picked up |
| Output | `Pump_Motor` | `BOOL` | Control output for the operation of the cleaning pump motor |
| Output | `Filling_Valve` | `BOOL` | Control output for the operation of the filling valve |
| Output | `Capping_Machine` | `BOOL` | Control output for the operation of the capping machine |
| Output | `Packing_Machine` | `BOOL` | Control output for the operation of the packing machine |
| Output | `Completion_Light` | `BOOL` | Indicator light for packaging completion |