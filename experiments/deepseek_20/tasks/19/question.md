# Mechanical Arm Control

- **Difficulty:** Hard (hard)

## Requirements

Design a PLC program to control an automated mechanical arm that performs handling tasks on the production line. The mechanical arm has six basic actions: down, up, left, right, grip, and release. The operating modes of the mechanical arm include four types: manual, single step, single cycle, and continuous.
Control requirements:
1. Manual mode: Allows the operator to control each action of the mechanical arm individually through the control panel, provided it is not yet in position. For example, pressing the down button (DownButton=1), if not at the down position (DownLimitSwitch=0), then move down (MoveDown=1); if at the down position (DownLimitSwitch=1), stop moving down. Releasing the down button also stops the movement down.
2. Single step mode: The mechanical arm automatically executes one action according to the preset program, and the operator needs to confirm after each action is completed to execute the next action.
The initial position of the mechanical arm is at the top left.
When the start button is pressed once, the mechanical arm executes the down command MoveDown, and stops after reaching the down position.
When the start button is pressed again, the mechanical arm executes the grip command ActivateGrip, and stops after gripping.
When the start button is pressed again, the mechanical arm executes the up command MoveUp, and stops after reaching the up position.
When the start button is pressed, the mechanical arm executes the right command MoveRight, and stops after reaching the right position.
When the start button is pressed, the mechanical arm executes the down command MoveDown, and stops after reaching the down position.
When the start button is pressed, the mechanical arm executes the release command ActivateRelease, and stops after releasing.
When the start button is pressed again, the mechanical arm executes the up command MoveUp, and stops after reaching the up position.
When the start button is pressed again, the mechanical arm executes the left command MoveLeft, and stops after reaching the left position.
Then starts the cycle again from the beginning
3. Single cycle mode: The mechanical arm automatically completes a full handling cycle, including all preset actions, and stops at the end of the cycle waiting for the operator's instruction.
The initial position of the mechanical arm is at the top left, when the start button is pressed:
The mechanical arm first moves down, then grips after reaching the down position, moves up after gripping, moves right after reaching the up position, moves down after reaching the right position, releases after reaching the down position, moves up after releasing, moves left after reaching the up position, and stops after reaching the left position.
4. Continuous mode: The initial position of the mechanical arm is at the top left, when the start button is pressed, the mechanical arm continuously executes the handling cycle of the single cycle mode.
5. The emergency stop function can stop all actions of the mechanical arm at any time.

Use GripLimitSwitch and ReleaseLimitSwitch as the completion feedback for gripping and releasing respectively. The caller keeps the four mode-selection inputs mutually exclusive.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `ManualMode` | `BOOL` | Manual mode |
| Input | `SingleStepMode` | `BOOL` | Single step mode |
| Input | `SingleCycleMode` | `BOOL` | Single cycle mode |
| Input | `ContinuousMode` | `BOOL` | Continuous mode |
| Input | `EmergencyStop` | `BOOL` | Emergency stop signal<br>FALSE: Emergency stop triggered<br>TRUE: No emergency stop triggered |
| Input | `Start` | `BOOL` | Start operation |
| Input | `DownButton` | `BOOL` | Down button |
| Input | `UpButton` | `BOOL` | Up button |
| Input | `LeftButton` | `BOOL` | Left button |
| Input | `RightButton` | `BOOL` | Right button |
| Input | `GripButton` | `BOOL` | Grip button |
| Input | `ReleaseButton` | `BOOL` | Release button |
| Input | `DownLimitSwitch` | `BOOL` | Down position limit switch |
| Input | `UpLimitSwitch` | `BOOL` | Up position limit switch |
| Input | `LeftLimitSwitch` | `BOOL` | Left position limit switch |
| Input | `RightLimitSwitch` | `BOOL` | Right position limit switch |
| Input | `GripLimitSwitch` | `BOOL` | Grip position limit switch |
| Input | `ReleaseLimitSwitch` | `BOOL` | Release position limit switch |
| Output | `MoveDown` | `BOOL` | Down command |
| Output | `MoveUp` | `BOOL` | Up command |
| Output | `MoveLeft` | `BOOL` | Left command |
| Output | `MoveRight` | `BOOL` | Right command |
| Output | `ActivateGrip` | `BOOL` | Grip command |
| Output | `ActivateRelease` | `BOOL` | Release command |