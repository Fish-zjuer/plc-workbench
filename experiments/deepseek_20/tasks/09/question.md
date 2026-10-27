# Calculate Moving Average

- **Difficulty:** Medium (medium)

## Requirements

Write a function block FB that calculates and updates a moving arithmetic mean. The moving arithmetic mean is a method of averaging over consecutive data points, where each new data point replaces the oldest data point, and then the average is recalculated.

1. When cyclicExecution is TRUE, a new data value is automatically read and the moving average average is updated every scan cycle.
2. Provide an external trigger signal trigger, which reads a new data value and updates the moving average upon each rising edge.
3. Provide a reset function reset, which resets the moving average calculation when the reset signal is TRUE. If the window size is less than 1 or greater than 100, output an error status and status code.

The status parameter indicates the execution status of the program:
- 16#0000: Execution successful
- 16#8200: Window length setting error, please set a value between 1 and 100.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `cyclicExecution` | `BOOL` | When TRUE, periodic reading is performed, and trigger has no effect |
| Input | `trigger` | `BOOL` | External trigger signal, reads value upon each rising edge |
| Input | `value` | `LREAL` | Newly read data value |
| Input | `windowSize` | `INT` | The window size for the moving average, which must be between 1 and 100 |
| Input | `reset` | `BOOL` | Reset signal, resets the moving average calculation when TRUE |
| Output | `average` | `LREAL` | The moving average |
| Output | `windowSizeReached` | `BOOL` | FALSE: Maximum window width not yet reached TRUE: Maximum window width has been reached |
| Output | `error` | `BOOL` | FALSE: No error occurred TRUE: An error occurred during the execution of FB |
| Output | `status` | `WORD` | Status code |