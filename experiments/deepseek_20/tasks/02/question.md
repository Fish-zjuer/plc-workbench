# Dual-Word Edge Detection

- **Difficulty:** Easy (easy)

## Requirements

Write a function block FB that checks for rising and falling edges in each bit of a dual-word (DWord) input value every cycle. The function block should be able to detect and report changes, rising edges, and falling edges in the input value.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `value` | `DWORD` | The input value to be checked for changes and edge triggering |
| Output | `hasChanged` | `BOOL` | True indicates that the input value has changed |
| Output | `hasRisingEdges` | `BOOL` | True indicates that rising edges have occurred in the input value |
| Output | `risingBits` | `DWORD` | The bit stream of rising edges, where each bit indicates whether the corresponding input bit has experienced a rising edge (1 for a rising edge, 0 for no rising edge) |
| Output | `noOfRisingBits` | `USINT` | The number of rising edges in the input value |
| Output | `hasFallingEdges` | `BOOL` | True indicates that falling edges have occurred in the input value |
| Output | `fallingBits` | `DWORD` | The bit stream of falling edges, where each bit indicates whether the corresponding input bit has experienced a falling edge (1 for a falling edge, 0 for no falling edge) |
| Output | `noOfFallingBits` | `USINT` | The number of falling edges in the input value |