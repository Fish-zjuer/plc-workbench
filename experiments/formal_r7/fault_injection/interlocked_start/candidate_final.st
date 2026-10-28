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

(* Edge detection uses previous scan value; block initial prevStart = FALSE *)
startEdge := start AND NOT prevStart;
prevStart := start;

(* Stop / interlock dominate any simultaneous start edge *)
IF stop OR NOT permit THEN
  running := FALSE;
ELSIF startEdge THEN
  running := TRUE;
END_IF;

END_FUNCTION_BLOCK
