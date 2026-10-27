# Flexible Processing Control

- **Difficulty:** Hard (hard)

## Requirements

An automated production line consists of 5 workstations: numbered 1# to 5# from left to right. The 1# station is used for raw material loading, stations 2# to 4# are used for product processing, and the 5# station is used for finished product output and storage.
There is a motor in the production line, responsible for moving the product from one workstation to the next. Each workstation has a sensor (used to detect if the product has arrived).
Each product has a different sequence and number of processing steps, specified by the process sequence 'processSequence'. The processSequence is an array type, storing the sequence numbers of the workstations, and the system automatically sends the raw materials to the corresponding workstation for processing based on the station number.
Control requirements:
At the start of production, when the sensor at the 1# station (sensor1) detects the raw material, the start button at the 1# station (station1Start) is pressed. The system queries the first element of the process sequence 'processSequence', starts the conveyor to move the raw material to the corresponding workstation, and stops after delivery. Upon receiving the processing completion signal from the corresponding workstation (station2Complete to station4Complete), it continues to query the next element of the process sequence 'processSequence', determines the direction of the conveyor, and starts the conveyor (conveyorLeft, conveyorRight). This continues until the product is delivered to the 5# workstation.

processLength specifies the active sequence length, from 1 through 8, starting at processSequence[1]. The final active entry is output station 5; other active entries are processing stations 2 through 4. The caller supplies a sequence satisfying this contract.

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `processLength` | `USINT` | Active process-sequence length, 1..8; the final active entry must be station 5. |
| Input | `sensor1` | `BOOL` | Sensor at 1# station |
| Input | `sensor2` | `BOOL` | Sensor at 2# station |
| Input | `sensor3` | `BOOL` | Sensor at 3# station |
| Input | `sensor4` | `BOOL` | Sensor at 4# station |
| Input | `sensor5` | `BOOL` | Sensor at 5# station |
| Input | `station1Start` | `BOOL` | Start button at 1# station |
| Input | `station2Complete` | `BOOL` | Processing completion signal at 2# station |
| Input | `station3Complete` | `BOOL` | Processing completion signal at 3# station |
| Input | `station4Complete` | `BOOL` | Processing completion signal at 4# station |
| Input | `processSequence` | `ARRAY[1..8] OF USINT` | Processing sequence |
| Output | `conveyorLeft` | `BOOL` | Conveyor turns left |
| Output | `conveyorRight` | `BOOL` | Conveyor turns right |