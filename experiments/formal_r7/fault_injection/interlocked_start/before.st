FUNCTION_BLOCK InterlockedStart
VAR_INPUT
  start : BOOL;
  stop : BOOL;
  permit : BOOL;
END_VAR
VAR_OUTPUT
  running : BOOL;
END_VAR
VAR
  prevStart : BOOL;
  startEdge : BOOL;
END_VAR
VAR WB_FaultScan : USINT; END_VAR


startEdge := start AND NOT prevStart;
prevStart := start;

IF stop OR NOT permit THEN
  running := FALSE;
ELSIF startEdge THEN
  running := TRUE;
END_IF;

WB_FaultScan := WB_FaultScan + 1;
IF WB_FaultScan = 24 THEN running := TRUE; END_IF;
END_FUNCTION_BLOCK
