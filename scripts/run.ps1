# Keep Python switches such as -p/-s out of PowerShell's common-parameter binder.
$Arguments = $args
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'activate.ps1')
. (Join-Path $PSScriptRoot 'runtime-path.ps1')
$workbenchPython = Get-WorkbenchPython -ProjectRoot $workbenchRoot
Push-Location -LiteralPath $workbenchRoot
try { & $workbenchPython -X utf8 -B @Arguments; $workbenchExit = $LASTEXITCODE }
finally { Pop-Location }
exit $workbenchExit
