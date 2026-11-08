TYPE ST_Recipe :
   STRUCT
      recipeID : INT;
      ingredientType : INT;
      ingredientRatio : REAL;
      productionTemperature : REAL;
   END_STRUCT;
END_TYPE

FUNCTION_BLOCK Q17

VAR_INPUT
    addRecipe : BOOL;
    deleteRecipe : BOOL;
    modifyRecipe : BOOL;
    queryRecipe : BOOL;
    recipeIn : ST_Recipe;
END_VAR
VAR_OUTPUT
    recipeAdded : BOOL;
    recipeDeleted : BOOL;
    recipeModified : BOOL;
    recipeQueryResult : ST_Recipe;
    error : BOOL;
    status : WORD;
END_VAR
VAR_IN_OUT
    recipe : ARRAY[1 .. 10] OF ST_Recipe;
END_VAR
VAR
    i : INT;
    matchIdx : INT;
    freeIdx : INT;
    dupFound : BOOL;
END_VAR
VAR_INPUT
WBTEMP_0 : INT;
WBTEMP_1 : INT;
WBTEMP_2 : INT;
WBTEMP_3 : BOOL;
END_VAR

     
i := WBTEMP_0;
matchIdx := WBTEMP_1;
freeIdx := WBTEMP_2;
dupFound := WBTEMP_3;
    recipeAdded := FALSE;
    recipeDeleted := FALSE;
    recipeModified := FALSE;
    error := FALSE;
    status := 16#0000;

    matchIdx := 0;
    freeIdx := 0;
    dupFound := FALSE;
    FOR i := 1 TO 10 DO
        IF recipe[i].recipeID = 0 AND freeIdx = 0 THEN
            freeIdx := i;
        END_IF;
        IF recipeIn.recipeID <> 0 AND recipe[i].recipeID = recipeIn.recipeID THEN
            dupFound := TRUE;
            IF matchIdx = 0 THEN
                matchIdx := i;
            END_IF;
        END_IF;
    END_FOR;

    IF queryRecipe THEN
        IF matchIdx = 0 THEN
            error := TRUE;
            status := 16#8001;
        ELSE
            recipeQueryResult := recipe[matchIdx];
        END_IF;
    ELSIF addRecipe THEN
        IF dupFound THEN
            error := TRUE;
            status := 16#8002;
        ELSIF freeIdx = 0 THEN
            error := TRUE;
            status := 16#8003;
        ELSE
            recipe[freeIdx] := recipeIn;
            recipeAdded := TRUE;
        END_IF;
    ELSIF deleteRecipe THEN
        IF matchIdx = 0 THEN
            error := TRUE;
            status := 16#8004;
        ELSE
            recipe[matchIdx].recipeID := 0;
            recipeDeleted := TRUE;
        END_IF;
    ELSIF modifyRecipe THEN
        IF matchIdx = 0 THEN
            error := TRUE;
            status := 16#8005;
        ELSE
            recipe[matchIdx] := recipeIn;
            recipeModified := TRUE;
        END_IF;
    END_IF;
END_FUNCTION_BLOCK