FUNCTION_BLOCK IPv4Parser
VAR_INPUT
    ipText : STRING(254);
END_VAR
VAR_OUTPUT
    ipValue : UDINT;
END_VAR
VAR
    TextLength    : INT;
    Position      : INT;
    SegmentCount  : INT;
    SegmentLength : INT;
    SegmentValue  : UINT;
    DigitValue    : UINT;
    CharacterText : STRING(1);
    ParsedValue   : UDINT;
    Valid         : BOOL;
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
        (* MID extracts one character without string subscript access. *)
        CharacterText := MID(ipText, 1, Position);

        IF CharacterText = '.' THEN
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
        ELSE
            IF (CharacterText < '0') OR (CharacterText > '9') THEN
                Valid := FALSE;
            ELSE
                DigitValue := STRING_TO_UINT(CharacterText);
                SegmentLength := SegmentLength + 1;
                SegmentValue := (SegmentValue * UINT#10) + DigitValue;
                IF SegmentValue > UINT#255 THEN
                    Valid := FALSE;
                END_IF;
            END_IF;
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
