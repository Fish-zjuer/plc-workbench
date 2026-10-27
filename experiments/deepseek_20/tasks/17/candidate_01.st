TYPE ST_Recipe :
STRUCT
    recipeID : INT;                 (* 配方号，0 表示空槽 *)
    ingredientType : INT;           (* 原料类型 *)
    ingredientRatio : REAL;         (* 原料配比 *)
    productionTemperature : REAL;   (* 生产温度 *)
END_STRUCT
END_TYPE

FUNCTION_BLOCK Q17
VAR_INPUT
    addRecipe : BOOL;               (* 添加配方请求 *)
    deleteRecipe : BOOL;            (* 删除配方请求 *)
    modifyRecipe : BOOL;            (* 修改配方请求 *)
    queryRecipe : BOOL;             (* 查询配方请求 *)
    recipeIn : ST_Recipe;           (* 输入配方 *)
END_VAR
VAR_OUTPUT
    recipeAdded : BOOL;             (* 添加成功指示 *)
    recipeDeleted : BOOL;           (* 删除成功指示 *)
    recipeModified : BOOL;          (* 修改成功指示 *)
    recipeQueryResult : ST_Recipe;  (* 查询结果 *)
    error : BOOL;                   (* 错误状态 *)
    status : WORD;                  (* 状态码 *)
END_VAR
VAR_IN_OUT
    recipe : ARRAY[1..10] OF ST_Recipe;  (* 配方数据库 *)
END_VAR
VAR
    i : INT;
    found : BOOL;
    dup : BOOL;
    emptySlot : INT;
END_VAR

(* ---- 输出复位 ---- *)
recipeAdded := FALSE;
recipeDeleted := FALSE;
recipeModified := FALSE;
error := FALSE;
status := 16#0000;

(* 查找匹配项与最小下标的空槽 *)
found := FALSE;
dup := FALSE;
emptySlot := 0;
FOR i := 1 TO 10 DO
    IF recipe[i].recipeID = recipeIn.recipeID THEN
        found := TRUE;
    END_IF;
    IF recipe[i].recipeID = 0 AND emptySlot = 0 THEN
        emptySlot := i;
    END_IF;
END_FOR;
dup := found;

(* ---- 查询 ---- *)
IF queryRecipe THEN
    IF found THEN
        recipeQueryResult := recipe[i - 1];
        (* 按循环结束时的 i 无法定位，下面用重新搜索确保正确 *)
    END_IF;
END_IF;

(* ---- 添加 ---- *)
IF addRecipe THEN
    IF dup THEN
        error := TRUE;
        status := 16#8002;
    ELSIF emptySlot = 0 THEN
        error := TRUE;
        status := 16#8003;
    ELSE
        recipe[emptySlot] := recipeIn;
        recipeAdded := TRUE;
    END_IF;
END_IF;

(* ---- 删除 ---- *)
IF deleteRecipe THEN
    IF NOT found THEN
        error := TRUE;
        status := 16#8004;
    ELSE
        FOR i := 1 TO 10 DO
            IF recipe[i].recipeID = recipeIn.recipeID THEN
                recipe[i].recipeID := 0;
                recipe[i].ingredientType := 0;
                recipe[i].ingredientRatio := 0.0;
                recipe[i].productionTemperature := 0.0;
            END_IF;
        END_FOR;
        recipeDeleted := TRUE;
    END_IF;
END_IF;

(* ---- 修改 ---- *)
IF modifyRecipe THEN
    IF NOT found THEN
        error := TRUE;
        status := 16#8005;
    ELSE
        FOR i := 1 TO 10 DO
            IF recipe[i].recipeID = recipeIn.recipeID THEN
                recipe[i] := recipeIn;
            END_IF;
        END_FOR;
        recipeModified := TRUE;
    END_IF;
END_IF;

(* ---- 查询（重新定位，避免使用循环残留下标） ---- *)
IF queryRecipe AND NOT error THEN
    FOR i := 1 TO 10 DO
        IF recipe[i].recipeID = recipeIn.recipeID THEN
            recipeQueryResult := recipe[i];
        END_IF;
    END_FOR;
    IF NOT found THEN
        error := TRUE;
        status := 16#8001;
    END_IF;
END_IF;

END_FUNCTION_BLOCK
