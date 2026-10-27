# Recipe Management System

- **Difficulty:** Hard (hard)

## Requirements

A factory's production line needs to produce a variety of products based on different recipes. The control center of the production line requires a recipe management system that allows operators to add, delete, modify, and query recipe data.
Control requirements:
Recipe data should include recipe number, raw material type, raw material ratio, and production temperature.
The system should allow input of new recipe data and store it in the recipe database.
The system should allow deletion or modification of existing recipe data by recipe number.
The system should allow querying recipe details by recipe number and output the recipe.
Notes:
1. Recipes are constructed using the ST_Recipe data type, which includes recipe number (recipeID), raw material type (ingredientType), raw material ratio (ingredientRatio), and production temperature (productionTemperature). The recipe database can store up to 10 recipes, constructed with ARRAY[1..10] OF ST_Recipe, where recipe numbers must not be duplicated, and a recipe number of 0 indicates an empty slot.
2. When a query recipe request signal (queryRecipe) is triggered, the system first compares the recipe number (recipeID) from the input recipe (recipeIn) with all recipes in the recipe database recipe. If the number does not exist, an error status (error=true) and error code (status=16#8001) are output. If the number exists, the recipe is output to the recipe query result (recipeQueryResult).
3. When an add recipe request signal (addRecipe) is triggered, the system first compares the recipe number (recipeID) from the input recipe (recipeIn) with all recipes in the recipe database (recipe). If a duplicate number exists, an error status (error=true) and error code (status=16#8002) are output. If there is no empty slot in the recipe database (recipe), an error status (error=true) and error code (status=16#8003) are output. If there are no errors, the input recipe (recipeIn) is stored in the recipe database (recipe), prioritizing the empty slot with the smallest array index.
4. When a delete recipe request signal (deleteRecipe) is triggered, the system first compares the recipe number (recipeID) from the input recipe (recipeIn) with all recipes in the recipe database (recipe). If the number does not exist, an error status (error=true) and error code (status=16#8004) are output. If the number exists, the recipe is deleted, i.e., the recipe number (recipeID) in the recipe database (recipe) is set to 0.
5. When a modify recipe request signal (modifyRecipe) is triggered, the system first compares the recipe number (recipeID) from the input recipe (recipeIn) with all recipes in the recipe database (recipe). If the number does not exist, an error status (error=true) and error code (status=16#8005) are output. If the number exists, the recipe is replaced with the input recipe (recipeIn).

## Interface Definition

| Direction | Variable/Field | Data Type | Description |
| --- | --- | --- | --- |
| Input | `addRecipe` | `BOOL` | Add Recipe Request Signal |
| Input | `deleteRecipe` | `BOOL` | Delete Recipe Request Signal |
| Input | `modifyRecipe` | `BOOL` | Modify Recipe Request Signal |
| Input | `queryRecipe` | `BOOL` | Query Recipe Request Signal |
| Input | `recipeIn` | `ST_Recipe` | Input Recipe |
| Output | `recipeAdded` | `BOOL` | Recipe Added Success Indicator |
| Output | `recipeDeleted` | `BOOL` | Recipe Deleted Success Indicator |
| Output | `recipeModified` | `BOOL` | Recipe Modified Success Indicator |
| Output | `recipeQueryResult` | `ST_Recipe` | Recipe Query Result Output |
| Output | `error` | `BOOL` | Error Status Indicator<br>FALSE: No Error Occurred<br>TRUE: Execution Error |
| Output | `status` | `WORD` | Status Code |
| Input/Output | `recipe` | `ARRAY[1..10] OF ST_Recipe` | Recipe Database |

**Data type `ST_Recipe`**

| Field | Data Type | Description |
| --- | --- | --- |
| `recipeID` | `INT` | Recipe identifier; zero denotes an unused database slot. |
| `ingredientType` | `INT` | Ingredient-type identifier. |
| `ingredientRatio` | `REAL` | Ingredient proportion. |
| `productionTemperature` | `REAL` | Production temperature. |