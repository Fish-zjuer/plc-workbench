FUNCTION_BLOCK AcknowledgeLatch
VAR_INPUT
    fault : BOOL;
    acknowledge : BOOL;
END_VAR
VAR_OUTPUT
    alarm : BOOL := FALSE;
END_VAR
VAR
    prevAck : BOOL := FALSE;
    ackRising : BOOL := FALSE;
END_VAR

ackRising := acknowledge AND NOT prevAck;
prevAck := acknowledge;

IF fault THEN
    alarm := TRUE;
ELSIF ackRising THEN
    alarm := FALSE;
END_IF;

END_FUNCTION_BLOCK