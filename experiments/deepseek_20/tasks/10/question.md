# Temperature Logic Control

- **Difficulty:** Medium (medium)

## Requirements

Write a function block FB to implement a temperature control logic. The program should include the following functions:
1. Read the value of the temperature sensor through an analog input module.
2. Compare the read temperature value TemperatureSensorInput with the set temperature value SetTemperature.
3. If the actual temperature is lower than the set temperature, start the heater HeaterOutput.
4. If the actual temperature is higher than the set temperature, turn off the heater HeaterOutput.
5. If the heater works continuously for more than a certain period (for convenience, using 5s), it should trigger an overheating protection, automatically turn off the heater, and must wait for a certain period (for convenience, using 3s) before the overheating protection can be lifted.
6. Provide status indication, displaying the current temperature, set temperature, heater status, and whether overheating protection is triggered.
7. Provide temperature sensor fault judgment, if the read temperature value TemperatureSensorInput is less than 0 or greater than 100, it is considered a sensor fault, and the heater should be turned off.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `TemperatureSensorInput` | `REAL` | The input value of the temperature sensor, i.e., the actual temperature |
| Input | `SetTemperature` | `REAL` | The set temperature value |
| Output | `CurrentTemperature` | `REAL` | Display of the current temperature |
| Output | `SetTempDisplay` | `REAL` | Display of the set temperature |
| Output | `HeaterStatus` | `BOOL` | Display of the heater status |
| Output | `OverheatProtection` | `BOOL` | Display of the overheating protection status |
| Output | `HeaterOutput` | `BOOL` | The control output of the heater |