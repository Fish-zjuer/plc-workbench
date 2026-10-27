# Automated Production Line Control

- **Difficulty:** Medium (medium)

## Requirements

A simple automated production line consists of three workstations: Workstation A, Workstation B, and Workstation C. The product needs to go through these three stations in sequence to be considered fully completed. There is a motor in the production line that is responsible for moving the product from one workstation to the next. The sequence of the line is from Workstation A to Workstation B, and then to Workstation C. Each workstation has a sensor (used to detect if the product has arrived) and a button (used to trigger the signal that the station's processing is complete).
Control requirements:
1. Mode Switching: The mode switch (Mode) is used to switch between manual and automatic modes of the production line.
2. Manual Mode: In manual mode, the forward rotation button (ForwardButton) controls the forward rotation of the motor, and the reverse rotation button (ReverseButton) controls the reverse rotation of the motor. Forward and reverse rotation operations need to be interlocked and cannot be performed simultaneously.
3. Automatic Mode:
   - When the product arrives at Workstation A, SensorA detects the product, and after the operator triggers the processing complete signal via ButtonA, the motor starts forward rotation to move the product to Workstation B.
   - When the product arrives at Workstation B, SensorB detects the product, the motor stops, and after the operator triggers the processing complete signal via ButtonB, the motor starts forward rotation to move the product to Workstation C.
   - When the product arrives at Workstation C, SensorC detects the product, the motor stops, and after the operator triggers the processing complete signal via ButtonC, the completion indicator light (CompletionLight) turns on, indicating that the product processing is complete. When the product is taken away, i.e., SensorC no longer detects the product, the completion indicator light (CompletionLight) turns off.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `Mode` | `BOOL` | Used to switch the production line between manual and automatic modes, 0=manual mode, 1=automatic mode |
| Input | `ForwardButton` | `BOOL` | Forward rotation button |
| Input | `ReverseButton` | `BOOL` | Reverse rotation button |
| Input | `SensorA` | `BOOL` | Sensor A |
| Input | `SensorB` | `BOOL` | Sensor B |
| Input | `SensorC` | `BOOL` | Sensor C |
| Input | `ButtonA` | `BOOL` | Button A |
| Input | `ButtonB` | `BOOL` | Button B |
| Input | `ButtonC` | `BOOL` | Button C |
| Output | `MotorForward` | `BOOL` | Motor forward rotation output |
| Output | `MotorReverse` | `BOOL` | Motor reverse rotation output |
| Output | `CompletionLight` | `BOOL` | Indicator light for product processing completion |