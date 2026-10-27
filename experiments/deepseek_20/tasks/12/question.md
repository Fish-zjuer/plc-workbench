# Slab Thickness Alarm and Fault History

- **Difficulty:** Medium (medium)

## Requirements

Monitor slab-thickness faults on a stone-cutting line, including minimum alarm holding, fault counting, normal-cutting runtime accumulation and a history of the five most recent faults.

1. When THICKNESS_SIGNAL_VALID is TRUE, THICKNESS_FAULT indicates that thickness deviation exceeds tolerance. Activate THICKNESS_ALARM immediately when the fault becomes TRUE, and hold each triggered alarm for at least 500 ms. Keep the alarm active while the fault persists.
2. On each FALSE-to-TRUE transition of a valid fault signal, increment Slab_Fault_Counter and store the current FaultTimestamp in element 0 of Slab_Fault_History. Shift older entries toward higher indices, retaining only the five most recent entries.
3. Accumulate Slab_Runtime_Accumulator using CycleTime only while CUTTING_RUN is TRUE, the thickness signal is valid and no thickness fault is present. Otherwise preserve the accumulated value.
4. At power-up or whenever THICKNESS_SIGNAL_VALID is FALSE, switch off the alarm and clear its holding state. Do not add fault records or accumulate normal runtime while the signal is invalid.
5. At power-up, initialize the fault count, accumulated runtime and all five history entries to zero. Statistics and history are for observation and maintenance only; they must not alter the cutting equipment's operating permissive, and external callers must not modify history entries.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `THICKNESS_FAULT` | `BOOL` | Thickness deviation exceeds the permitted tolerance. |
| Input | `THICKNESS_SIGNAL_VALID` | `BOOL` | Thickness-signal validity; FALSE means the signal is lost or unavailable. |
| Input | `CUTTING_RUN` | `BOOL` | Actual cutting-equipment running status. |
| Input | `FaultTimestamp` | `DINT` | Current timestamp in seconds, used as the fault-record identifier. |
| Input | `CycleTime` | `TIME` | Actual elapsed interval represented by this invocation; must be positive. |
| Output | `THICKNESS_ALARM` | `BOOL` | Thickness alarm with a minimum 500 ms hold duration. |
| Output | `Slab_Fault_Counter` | `UINT` | Number of valid thickness-fault occurrences. |
| Output | `Slab_Runtime_Accumulator` | `LTIME` | Accumulated normal-cutting runtime. |
| Output | `Slab_Fault_History` | `ARRAY[0..4] OF DINT` | Five most recent fault timestamps; index 0 is newest; read-only to callers. |