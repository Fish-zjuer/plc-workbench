# IPv4 Parsing with Format and Range Checks

- **Difficulty:** Medium (medium)

## Requirements

Design a PLC function block in Structured Text (ST) that parses a dotted-decimal IPv4 string into a 32-bit unsigned integer.

1. ipText must contain four nonempty decimal-digit segments separated by periods. Each segment must have a value from 0 through 255.
2. Assemble the address in network byte order: the first segment occupies the most significant 8 bits and the fourth occupies the least significant 8 bits. Write the result to ipValue.
3. Set ipValue to 0 for malformed input, a nondigit segment, an incorrect segment count or any out-of-range segment. The valid address 0.0.0.0 also produces 0.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `ipText` | `STRING(254)` | IPv4 text to parse, with a capacity of 254 characters. A valid dotted-decimal address requires at most 15 characters. |
| Output | `ipValue` | `UDINT` | 32-bit address in network byte order; zero for invalid input. |

Submission packaging only: use FUNCTION_BLOCK IPv4Parser. Keep exactly the supplied input/output names and data types. Local internal state may be added. Target CODESYS ST.
