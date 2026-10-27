# Production Control

- **Difficulty:** Hard (hard)

## Requirements

An automated production line consists of 5 workstations: material loading station, cleaning station, weighing station, firing station, and finished product station. The production line has a motor responsible for moving products from one workstation to the next, the sequence of the line is from the material loading station, cleaning station, weighing station, firing station, to the finished product station. Each workstation has a sensor (used to detect if the product has arrived).
Control requirements:
1. Mode Switching: The mode switch (Mode) is used to switch between manual and automatic modes of the production line. 0 = manual mode, 1 = automatic mode.
2. Manual Mode: In manual mode, the forward rotation button (ForwardButton) controls the forward rotation of the motor, and the reverse rotation button (ReverseButton) controls the reverse rotation of the motor. Forward and reverse rotation operations need to be interlocked and cannot be performed simultaneously.
3. Automatic Mode:
   - When the material arrives at the material loading station, the SensorFeed detects the material, the motor starts forward rotation, and moves the material to the cleaning station.
   - When the material arrives at the cleaning station, the SensorWash detects the material, the motor stops, and upon receiving the signal washComplete after cleaning is finished, the motor starts forward rotation, moving the material to the weighing station.
   - When the material arrives at the weighing station, the SensorWeight detects the material, the motor stops, and upon receiving weightComplete after weighing is complete, the material is judged to be qualified based on the weight value. If the weight value is greater than or equal to 100 and less than or equal to 200, it is qualified, otherwise not.
     If the material is unqualified, the rejection command kick is initiated.
     If the material is qualified, the firing temperature is calculated based on the weight value. The calculation rule is that the weight value from 100 to 200 linearly corresponds to the temperature value from 500 to 550. The firing temperature firingTemp is output. At the same time, the motor starts forward rotation, moving the material to the firing station.
   - When the product arrives at the firing station, the SensorFiring detects the material, the motor stops, and upon receiving the signal firingComplete after firing is finished, the motor starts forward rotation, moving the product to the finished product station.
   - When the product arrives at the finished product station, the SensorOutput detects the product, the motor stops, and the completion light (CompletionLight) turns on, indicating that the product processing is complete. When the product is taken away, i.e., the SensorOutput does not detect the product, the completion light (CompletionLight) turns off.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `Mode` | `BOOL` | Used to switch the production line between manual and automatic modes, 0 = manual mode, 1 = automatic mode |
| Input | `ForwardButton` | `BOOL` | Forward rotation button |
| Input | `ReverseButton` | `BOOL` | Reverse rotation button |
| Input | `SensorFeed` | `BOOL` | Sensor at the material loading station detecting the arrival of materials |
| Input | `SensorWash` | `BOOL` | Sensor at the cleaning station detecting the arrival of materials |
| Input | `SensorWeight` | `BOOL` | Sensor at the weighing station detecting the arrival of materials |
| Input | `SensorFiring` | `BOOL` | Sensor at the firing station detecting the arrival of materials |
| Input | `SensorOutput` | `BOOL` | Sensor at the finished product station detecting the arrival of products |
| Input | `washComplete` | `BOOL` | Signal indicating completion of cleaning |
| Input | `weightComplete` | `BOOL` | Signal indicating completion of weighing |
| Input | `weight` | `REAL` | Weight value |
| Input | `firingComplete` | `BOOL` | Signal indicating completion of firing |
| Output | `MotorForward` | `BOOL` | Output for motor forward rotation |
| Output | `MotorReverse` | `BOOL` | Output for motor reverse rotation |
| Output | `kick` | `BOOL` | Rejection output |
| Output | `CompletionLight` | `BOOL` | Indicator light for product processing completion |
| Output | `firingTemp` | `REAL` | Firing temperature |