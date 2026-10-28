# Dot-source this file to use the project's private toolchain in this terminal.
$workbenchRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$workbenchToolchainFile = Join-Path $workbenchRoot '.runtime/toolchain.json'
if (Test-Path -LiteralPath $workbenchToolchainFile) {
    $workbenchTools = Get-Content -LiteralPath $workbenchToolchainFile -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($workbenchBin in $workbenchTools.path) {
        if ((Test-Path -LiteralPath $workbenchBin) -and ($env:PATH.Split(';') -notcontains $workbenchBin)) {
            $env:PATH = $workbenchBin + ';' + $env:PATH
        }
    }
    if ($workbenchTools.cxx) { $env:CXX = $workbenchTools.cxx }
}
$workbenchVenvBin = Join-Path $workbenchRoot '.venv/Scripts'
if ((Test-Path -LiteralPath $workbenchVenvBin) -and ($env:PATH.Split(';') -notcontains $workbenchVenvBin)) {
    $env:PATH = $workbenchVenvBin + ';' + $env:PATH
}
