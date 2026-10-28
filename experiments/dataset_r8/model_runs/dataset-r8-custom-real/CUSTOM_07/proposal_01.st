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
    valid : BOOL;
END_VAR

IF (NOT Enable) OR Trip THEN
    FeedSP := 0.0;
    ExtractionSP := 0.0;
    Error := FALSE;
ELSE
    valid := (FeedDemand >= 0.0) AND (FeedDemand <= 100.0)
         AND (FeedActual >= 0.0) AND (FeedActual <= 100.0)
         AND (ExtractionCapacity >= 0.0) AND (ExtractionCapacity <= 100.0);

    IF valid THEN
        FeedSP := MIN(FeedDemand, ExtractionCapacity);
        ExtractionSP := MAX(FeedDemand, FeedActual);
        Error := FALSE;
    ELSE
        FeedSP := 0.0;
        ExtractionSP := 0.0;
        Error := TRUE;
    END_IF
END_IF

END_FUNCTION_BLOCK