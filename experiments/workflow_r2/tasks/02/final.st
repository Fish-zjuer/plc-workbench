(*
  Public bank question 02: Dual-Word Edge Detection
  FB EdgeDetection

  Semantics:
    risingBits  = value AND NOT previousValue   (bit 0 -> 1)
    fallingBits = previousValue AND NOT value   (bit 1 -> 0)
    hasRisingEdges  = risingBits  <> 0
    hasFallingEdges = fallingBits <> 0
    hasChanged      = value <> previousValue
    noOfRisingBits / noOfFallingBits = bit counts of the masks (USINT)

  The first call is not scored by the bank: it initialises previousValue
  with the current value, so no edges are reported on the first scan.
*)

FUNCTION_BLOCK EdgeDetection
VAR_INPUT
    value : DWORD;
END_VAR
VAR_OUTPUT
    hasChanged     : BOOL;
    hasRisingEdges : BOOL;
    risingBits     : DWORD;
    noOfRisingBits : USINT;
    hasFallingEdges : BOOL;
    fallingBits    : DWORD;
    noOfFallingBits : USINT;
END_VAR
VAR
    previousValue : DWORD;
    initialised   : BOOL;
    i             : USINT;
END_VAR

IF NOT initialised THEN
    previousValue := value;
    initialised := TRUE;
END_IF

risingBits  := value AND (NOT previousValue);
fallingBits := previousValue AND (NOT value);

hasRisingEdges  := risingBits <> DWORD#0;
hasFallingEdges := fallingBits <> DWORD#0;

noOfRisingBits  := USINT#0;
noOfFallingBits := USINT#0;
FOR i := 0 TO 31 DO
    IF (risingBits AND SHL(DWORD#1, i)) <> DWORD#0 THEN
        noOfRisingBits := noOfRisingBits + USINT#1;
    END_IF
    IF (fallingBits AND SHL(DWORD#1, i)) <> DWORD#0 THEN
        noOfFallingBits := noOfFallingBits + USINT#1;
    END_IF
END_FOR

hasChanged := value <> previousValue;

previousValue := value;
END_FUNCTION_BLOCK
