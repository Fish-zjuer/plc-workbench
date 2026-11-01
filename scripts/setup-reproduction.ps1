param([switch]$SkipCodex, [switch]$WithOptionalLocalTests)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$requiredTools = @()
if (!$SkipCodex) { $requiredTools += @('node','npm.cmd') }
if ($WithOptionalLocalTests) { $requiredTools += @('git','node','npm.cmd','g++') }
foreach ($taskTool in ($requiredTools | Select-Object -Unique)) {
    if (!(Get-Command $taskTool -ErrorAction SilentlyContinue)) { throw "Install prerequisite and reopen terminal: $taskTool" }
}
& (Join-Path $PSScriptRoot 'setup.ps1') -ProjectLocal
if ($LASTEXITCODE -ne 0) { throw 'Python setup failed' }
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if ($WithOptionalLocalTests) { $env:CXX = (Get-Command 'g++').Source }
Push-Location $taskRoot
try {
    & $taskPython -X utf8 scripts/verify_reproduction_data.py
    if ($LASTEXITCODE -ne 0) { throw 'Dataset validation failed' }
    if ($WithOptionalLocalTests) {
        if (!(Test-Path -LiteralPath (Join-Path $taskRoot 'optional_local_tests/dataset_backend.py'))) {
            throw 'optional_local_tests was removed; restore it to enable local fallback tests'
        }
        & $taskPython -B -m optional_local_tests.backend_r4 build
        if ($LASTEXITCODE -ne 0) { throw 'R4 build failed' }
        & $taskPython -B -m optional_local_tests.backend_r4 activate
        if ($LASTEXITCODE -ne 0) { throw 'R4 activation failed' }
    }
    if (!$SkipCodex) {
        & npm.cmd install --prefix (Join-Path $taskRoot '.runtime/codex-0.80') --no-audit --no-fund '@openai/codex@0.80.0'
        if ($LASTEXITCODE -ne 0) { throw 'Codex CLI installation failed' }
    }
    Write-Host 'Ready. Configure DMXAPI and CODESYS in the web UI. Optional local tests are installed only with -WithOptionalLocalTests.'
} finally { Pop-Location }
