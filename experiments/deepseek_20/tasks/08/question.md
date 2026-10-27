# Analog Batch Processing

- **Difficulty:** Medium (medium)

## Requirements

Write a PLC function block that processes analog inputs in batches and converts them into engineering values.

1. analogValues supplies the raw-value array. channels supplies per-channel settings and receives conversion results. count specifies how many channels to process from the beginning of the arrays. The caller must provide count from zero through the smaller of the two array lengths. Match channels by ordinal position starting at each array's own lower bound. Read analogValues without modifying it.
2. Each channel is enabled by its enable field and converted according to measuringMode. Read configuration fields without modifying them; write only retVal and outputValue.
3. For measuringMode 0, perform non-temperature linear scaling: when bipolar is FALSE, map raw values 0..27648 to loLIM..hiLIM; when TRUE, map -27648..27648 to loLIM..hiLIM.
4. For measuringMode 1, perform standard-temperature conversion: outputValue is one tenth of the raw analog value.
5. For measuringMode 2, perform climatic-temperature conversion: outputValue is one hundredth of the raw analog value.
6. If measuringMode is not 0, 1 or 2, set that channel's retVal to 16#8001 and skip its conversion.
7. If hiLIM is less than or equal to loLIM, set that channel's retVal to 16#8002 and skip its conversion.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `count` | `DINT` | Number of channels to be converted |
| Input/Output | `analogValues` | `ARRAY[*] OF INT` | Variable-length analog array passed by reference to preserve its bounds. Read-only to the function block; no element may be modified. |
| Input/Output | `channels` | `ARRAY[*] OF ST_AnalogChannel` | Channel records passed by reference. Configuration fields are read-only; write only retVal and outputValue. |
| Input field | `channels[].enable` | `BOOL` | Channel conversion enable. Read-only to the function block. |
| Input field | `channels[].hiLIM` | `REAL` | Upper engineering-unit limit. Read-only to the function block. |
| Input field | `channels[].loLIM` | `REAL` | Lower engineering-unit limit. Read-only to the function block. |
| Input field | `channels[].bipolar` | `BOOL` | FALSE selects unipolar and TRUE selects bipolar operation. Read-only to the function block. |
| Input field | `channels[].measuringMode` | `INT` | 0 non-temperature, 1 standard temperature, 2 climatic temperature. Read-only to the function block. |
| Output field | `channels[].retVal` | `WORD` | Per-channel status code written by the function block. |
| Output field | `channels[].outputValue` | `REAL` | Converted value written by the function block. |

Rows named `channels[].fieldName` describe the element fields of ST_AnalogChannel, rather than additional function-block parameters.