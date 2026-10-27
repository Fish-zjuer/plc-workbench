FUNCTION_BLOCK MovingAverage
VAR_INPUT
    cyclicExecution : BOOL;
    trigger         : BOOL;
    value           : LREAL;
    windowSize      : INT;
    reset           : BOOL;
END_VAR
VAR_OUTPUT
    average          : LREAL;
    windowSizeReached : BOOL;
    error            : BOOL;
    status           : WORD;
END_VAR
VAR
    Samples       : ARRAY[1..100] OF LREAL;
    SampleCount   : INT := 0;
    NextIndex     : INT := 1;
    RunningSum    : LREAL := 0.0;
    PreviousTrigger : BOOL := FALSE;
    TriggerRise   : BOOL;
    PreviousWindowSize : INT := 0;
    ShouldSample  : BOOL;
END_VAR

TriggerRise := trigger AND NOT PreviousTrigger;
PreviousTrigger := trigger;

IF (windowSize < 1) OR (windowSize > 100) THEN
    error := TRUE;
    status := WORD#16#8200;
    windowSizeReached := FALSE;
ELSIF reset THEN
    error := FALSE;
    status := WORD#16#0000;
    SampleCount := 0;
    NextIndex := 1;
    RunningSum := 0.0;
    average := 0.0;
    windowSizeReached := FALSE;
    PreviousWindowSize := windowSize;
ELSE
    error := FALSE;
    status := WORD#16#0000;

    (* A changed window starts a fresh averaging history. *)
    IF PreviousWindowSize <> windowSize THEN
        SampleCount := 0;
        NextIndex := 1;
        RunningSum := 0.0;
        average := 0.0;
        PreviousWindowSize := windowSize;
    END_IF;

    ShouldSample := cyclicExecution OR ((NOT cyclicExecution) AND TriggerRise);
    IF ShouldSample THEN
        IF SampleCount < windowSize THEN
            SampleCount := SampleCount + 1;
        ELSE
            RunningSum := RunningSum - Samples[NextIndex];
        END_IF;

        Samples[NextIndex] := value;
        RunningSum := RunningSum + value;
        NextIndex := NextIndex + 1;
        IF NextIndex > windowSize THEN
            NextIndex := 1;
        END_IF;

        average := RunningSum / INT_TO_LREAL(SampleCount);
    END_IF;

    windowSizeReached := SampleCount >= windowSize;
END_IF;
END_FUNCTION_BLOCK
