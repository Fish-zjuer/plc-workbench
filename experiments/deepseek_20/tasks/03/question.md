# Alarm Handling

- **Difficulty:** Easy (easy)

## Requirements

In industrial automation systems, monitoring the status of equipment is crucial. When equipment parameters exceed the normal range, the system needs to issue an alarm. To avoid frequent triggering of alarms due to minor fluctuations in parameters, an alarm management system with hysteresis function needs to be implemented.
When Value is greater than hiLevel, trigger high alarm hiAlarm.
When Value is less than hiLevel-hystWindow, exit high alarm hiAlarm.
When Value is less than loLevel, trigger low alarm loAlarm.
When Value is greater than loLevel+hystWindow, exit low alarm loAlarm.
If loLevel is greater than or equal to hiLevel, output error error=true, status=16#8001, and exit the program
If the hysteresis window value hystWindow is greater than or equal to the deviation range between hiLevel and loLevel, output error error=true, status=16#8002

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `Value` | `REAL` | Input value |
| Input | `hiLevel` | `REAL` | High limit alarm value |
| Input | `loLevel` | `REAL` | Low limit alarm value |
| Input | `hystWindow` | `REAL` | Hysteresis window |
| Output | `hiAlarm` | `BOOL` | High limit alarm |
| Output | `loAlarm` | `BOOL` | Low limit alarm |
| Output | `error` | `BOOL` | FALSE: No error occurred;<br>TRUE: Error occurred during execution of FB |
| Output | `status` | `WORD` | Status code |