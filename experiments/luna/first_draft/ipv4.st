FUNCTION_BLOCK IPv4Parser
VAR_INPUT
    ipText : STRING(254);
END_VAR
VAR_OUTPUT
    ipValue : UDINT;
END_VAR
VAR
    TextLength  : INT;
    Position    : INT;
    SegmentCount : INT;
    SegmentLength : INT;
    SegmentValue : UINT;
    CharacterCode : BYTE;
    ParsedValue : UDINT;
    Valid       : BOOL;
END_VAR

ipValue := UDINT#0;
TextLength := LEN(ipText);
SegmentCount := 0;
SegmentLength := 0;
SegmentValue := UINT#0;
ParsedValue := UDINT#0;
Valid := (TextLength > 0) AND (TextLength <= 15);

IF Valid THEN
    FOR Position := 1 TO TextLength DO
        CharacterCode := ipText[Position];

        IF CharacterCode = BYTE#46 THEN
            IF (SegmentLength = 0) OR (SegmentValue > UINT#255) THEN
                Valid := FALSE;
            ELSE
                SegmentCount := SegmentCount + 1;
                IF SegmentCount > 3 THEN
                    Valid := FALSE;
                ELSE
                    ParsedValue := (ParsedValue * UDINT#256) + UINT_TO_UDINT(SegmentValue);
                    SegmentLength := 0;
                    SegmentValue := UINT#0;
                END_IF;
            END_IF;
        ELSIF (CharacterCode >= BYTE#48) AND (CharacterCode <= BYTE#57) THEN
            SegmentLength := SegmentLength + 1;
            SegmentValue := (SegmentValue * UINT#10) + BYTE_TO_UINT(CharacterCode - BYTE#48);
            IF SegmentValue > UINT#255 THEN
                Valid := FALSE;
            END_IF;
        ELSE
            Valid := FALSE;
        END_IF;
    END_FOR;

    IF (SegmentLength = 0) OR (SegmentValue > UINT#255) THEN
        Valid := FALSE;
    ELSE
        SegmentCount := SegmentCount + 1;
        IF SegmentCount <> 4 THEN
            Valid := FALSE;
        ELSE
            ParsedValue := (ParsedValue * UDINT#256) + UINT_TO_UDINT(SegmentValue);
        END_IF;
    END_IF;
END_IF;

IF Valid THEN
    ipValue := ParsedValue;
ELSE
    ipValue := UDINT#0;
END_IF;
END_FUNCTION_BLOCK
