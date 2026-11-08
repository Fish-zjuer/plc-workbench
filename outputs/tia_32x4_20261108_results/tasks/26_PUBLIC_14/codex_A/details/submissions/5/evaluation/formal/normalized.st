FUNCTION_BLOCK IPv4Parser

VAR_INPUT
    ipText : STRING[254];
END_VAR

VAR_OUTPUT
    ipValue : UDINT;
END_VAR

VAR
    i : INT;
    len : INT;
    segNo : INT;
    segVal : UDINT;
    digitCnt : INT;
    c : BYTE;
    bad : BOOL;
    v1 : UDINT;
    v2 : UDINT;
    v3 : UDINT;
    v4 : UDINT;
END_VAR
VAR_INPUT
WBTEMP_0 : INT;
WBTEMP_1 : INT;
WBTEMP_2 : INT;
WBTEMP_3 : UDINT;
WBTEMP_4 : INT;
WBTEMP_5 : BYTE;
WBTEMP_6 : BOOL;
WBTEMP_7 : UDINT;
WBTEMP_8 : UDINT;
WBTEMP_9 : UDINT;
WBTEMP_10 : UDINT;
END_VAR


     
i := WBTEMP_0;
len := WBTEMP_1;
segNo := WBTEMP_2;
segVal := WBTEMP_3;
digitCnt := WBTEMP_4;
c := WBTEMP_5;
bad := WBTEMP_6;
v1 := WBTEMP_7;
v2 := WBTEMP_8;
v3 := WBTEMP_9;
v4 := WBTEMP_10;
    ipValue := 0;
    v1 := 0;
    v2 := 0;
    v3 := 0;
    v4 := 0;
    segNo := 1;
    segVal := 0;
    digitCnt := 0;
    bad := FALSE;
    len := LEN(ipText);

    IF len = 0 OR len > 15 THEN
        bad := TRUE;
    END_IF;

    IF NOT bad THEN
        FOR i := 1 TO len DO
            c := ipText[i];
            IF c >= 48 AND c <= 57 THEN
                digitCnt := digitCnt + 1;
                IF digitCnt > 3 THEN
                    bad := TRUE;
                ELSE
                    segVal := segVal * 10 + DINT_TO_UDINT(BYTE_TO_DINT(c) - 48);
                END_IF;
            ELSIF c = 46 THEN
                IF digitCnt = 0 OR segVal > 255 THEN
                    bad := TRUE;
                ELSE
                    CASE segNo OF
                        1: v1 := segVal;
                        2: v2 := segVal;
                        3: v3 := segVal;
                        ELSE
                            bad := TRUE;
                    END_CASE;
                    segNo := segNo + 1;
                    segVal := 0;
                    digitCnt := 0;
                END_IF;
            ELSE
                bad := TRUE;
            END_IF;
        END_FOR;
    END_IF;

    IF NOT bad THEN
        IF digitCnt = 0 OR segVal > 255 OR segNo <> 4 THEN
            bad := TRUE;
        ELSE
            v4 := segVal;
        END_IF;
    END_IF;

    IF NOT bad THEN
        ipValue := (v1 * 16777216) + (v2 * 65536) + (v3 * 256) + v4;
    ELSE
        ipValue := 0;
    END_IF;
END_FUNCTION_BLOCK