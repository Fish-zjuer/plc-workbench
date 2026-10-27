param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime-path.ps1')
$runtimePython = Get-WorkbenchPython -ProjectRoot $projectRoot
if (!(Test-Path -LiteralPath $runtimePython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
    if (!(Test-Path -LiteralPath $runtimePython)) { throw 'Python environment setup failed; see the error above.' }
}
Push-Location -LiteralPath $projectRoot
try {
    if ($CheckOnly) { & $runtimePython -B -m plc_agent doctor }
    else { & $runtimePython -B -m plc_agent ui }
    $result = $LASTEXITCODE
} finally { Pop-Location }
exit $result
