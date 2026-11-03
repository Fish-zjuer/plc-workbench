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
    idx : INT;                      (* 命中的数据库下标，0 表示未命中 *)
    emptySlot : INT;                (* 最小下标的空槽，0 表示无空槽 *)
END_VAR

(* ---- 每个扫描周期复位输出 ---- *)
recipeAdded := FALSE;
recipeDeleted := FALSE;
recipeModified := FALSE;
error := FALSE;
status := 16#0000;

(* ---- 扫描数据库：命中下标 + 最小空槽 ---- *)
idx := 0;
emptySlot := 0;
FOR i := 1 TO 10 DO
    IF recipe[i].recipeID = recipeIn.recipeID AND recipeIn.recipeID <> 0 AND idx = 0 THEN
        idx := i;
    END_IF;
    IF recipe[i].recipeID = 0 AND emptySlot = 0 THEN
        emptySlot := i;
    END_IF;
END_FOR;

(* ---- 查询 ---- *)
IF queryRecipe THEN
    IF idx = 0 THEN
        error := TRUE;
        status := 16#8001;
    ELSE
        recipeQueryResult := recipe[idx];
    END_IF;
END_IF;

(* ---- 添加 ---- *)
IF addRecipe THEN
    IF idx <> 0 THEN
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

(* ---- 删除：recipeID 置 0 表示空槽 ---- *)
IF deleteRecipe THEN
    IF idx = 0 THEN
        error := TRUE;
        status := 16#8004;
    ELSE
        recipe[idx].recipeID := 0;
        recipe[idx].ingredientType := 0;
        recipe[idx].ingredientRatio := 0.0;
        recipe[idx].productionTemperature := 0.0;
        recipeDeleted := TRUE;
    END_IF;
END_IF;

(* ---- 修改 ---- *)
IF modifyRecipe THEN
    IF idx = 0 THEN
        error := TRUE;
        status := 16#8005;
    ELSE
        recipe[idx] := recipeIn;
        recipeModified := TRUE;
    END_IF;
END_IF;

END_FUNCTION_BLOCK
