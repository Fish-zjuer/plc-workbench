FUNCTION_BLOCK FB_CrusherExtraction

VAR_INPUT
  Enable : BOOL;
  Trip : BOOL;
  FeedDemand : LREAL;
  FeedActual : LREAL;
  ExtractionCapacity : LREAL;
END_VAR

VAR_OUTPUT
  FeedSP : LREAL;
  ExtractionSP : LREAL;
  Error : BOOL;
END_VAR

VAR
  active : BOOL;
  valid : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : BOOL;
WBTEMP_1 : BOOL;
END_VAR


     
active := WBTEMP_0;
valid := WBTEMP_1;
  active := Enable AND NOT Trip;

  valid := (FeedDemand >= 0.0) AND (FeedDemand <= 100.0)
            AND (FeedActual >= 0.0) AND (FeedActual <= 100.0)
            AND (ExtractionCapacity >= 0.0) AND (ExtractionCapacity <= 100.0);

  IF NOT active THEN
    FeedSP := 0.0;
    ExtractionSP := 0.0;
    Error := FALSE;
  ELSIF NOT valid THEN
    FeedSP := 0.0;
    ExtractionSP := 0.0;
    Error := TRUE;
  ELSE
    IF FeedDemand < ExtractionCapacity THEN
      FeedSP := FeedDemand;
    ELSE
      FeedSP := ExtractionCapacity;
    END_IF;

    IF FeedDemand > FeedActual THEN
      ExtractionSP := FeedDemand;
    ELSE
      ExtractionSP := FeedActual;
    END_IF;

    Error := FALSE;
  END_IF;
END_FUNCTION_BLOCK