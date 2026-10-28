FUNCTION_BLOCK FB_GateTelemetry
VAR_INPUT
  Reset : BOOL;
  FrameValid : BOOL;
  FrameSeq : UDINT;
  Ack : BOOL;
  DtMs : UDINT;
  TimeoutMs : UDINT;
END_VAR
VAR_OUTPUT
  Fresh : BOOL;
  AgeMs : UDINT;
  CommFault : BOOL;
  RemoteWritePermit : BOOL;
  Error : BOOL;
END_VAR
VAR
  known : BOOL;
  seq : UDINT;
  age : UDINT;
  fault : BOOL;
  validTiming : BOOL;
  freshNow : BOOL;
END_VAR

validTiming := (DtMs >= 1) AND (DtMs <= 1000) AND (TimeoutMs >= 1) AND (TimeoutMs <= 60000);

IF Reset THEN
  known := FALSE;
  seq := 0;
  age := 0;
  fault := TRUE;
  Fresh := FALSE;
  AgeMs := 0;
  CommFault := TRUE;
  RemoteWritePermit := FALSE;
  Error := FALSE;
ELSIF NOT validTiming THEN
  fault := TRUE;
  Fresh := FALSE;
  AgeMs := age;
  CommFault := TRUE;
  RemoteWritePermit := FALSE;
  Error := TRUE;
ELSE
  Error := FALSE;

  freshNow := FrameValid AND ((NOT known) OR (FrameSeq <> seq));

  IF freshNow THEN
    known := TRUE;
    seq := FrameSeq;
    age := 0;
  ELSE
    IF age + DtMs > 60000 THEN
      age := 60000;
    ELSE
      age := age + DtMs;
    END_IF;
  END_IF;

  Fresh := freshNow;
  AgeMs := age;

  IF freshNow AND Ack THEN
    fault := FALSE;
  ELSIF age >= TimeoutMs THEN
    fault := TRUE;
  END_IF;

  CommFault := fault;
  RemoteWritePermit := (NOT fault) AND (age < TimeoutMs);
END_IF;

END_FUNCTION_BLOCK