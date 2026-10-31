param([switch]$SkipCodex)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
foreach ($taskTool in @('git','node','npm.cmd','g++')) {
    if (!(Get-Command $taskTool -ErrorAction SilentlyContinue)) { throw "Install prerequisite and reopen terminal: $taskTool" }
}
& (Join-Path $PSScriptRoot 'setup.ps1') -ProjectLocal
if ($LASTEXITCODE -ne 0) { throw 'Python setup failed' }
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
$env:CXX = (Get-Command 'g++').Source
Push-Location $taskRoot
try {
    & $taskPython -X utf8 scripts/verify_reproduction_data.py
    if ($LASTEXITCODE -ne 0) { throw 'Dataset validation failed' }
    & $taskPython -B -m plc_agent.backend_r4 build
    if ($LASTEXITCODE -ne 0) { throw 'R4 build failed' }
    & $taskPython -B -m plc_agent.backend_r4 activate
    if ($LASTEXITCODE -ne 0) { throw 'R4 activation failed' }
    if (!$SkipCodex) {
        & npm.cmd install --prefix (Join-Path $taskRoot '.runtime/codex-0.80') --no-audit --no-fund '@openai/codex@0.80.0'
        if ($LASTEXITCODE -ne 0) { throw 'Codex CLI installation failed' }
    }
    Write-Host 'Local toolchain ready. Configure your own DMXAPI key and CODESYS in the web UI, then run compiler controls.'
} finally { Pop-Location }
