param(
    [switch]$PrepareOnly,
    [string]$Model = 'deepseek-flash',
    [string]$Ids = 'all',
    [ValidateRange(1,4)][int]$Repeats = 2,
    [ValidateRange(1,4)][int]$Concurrency = 2
)
$ErrorActionPreference = 'Stop'
$matrixRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime-path.ps1')
$matrixPython = Get-WorkbenchPython -ProjectRoot $matrixRoot
if (!(Test-Path -LiteralPath $matrixPython)) { throw 'Run scripts/setup.ps1 first' }
$matrixDrive = $null
$matrixMapping = $null
$matrixExit = 1
$matrixOldTemp = $env:TEMP
$matrixOldTmp = $env:TMP
Push-Location -LiteralPath $matrixRoot
try {
    # Alias this project only; do not replace an existing drive or change ACLs.
    foreach ($matrixLetter in @('V','W','X','Y','Z')) {
        if (!(Test-Path -LiteralPath ($matrixLetter + ':\'))) {
            $matrixDrive = $matrixLetter + ':'
            & subst.exe $matrixDrive $matrixRoot
            if ($LASTEXITCODE -ne 0) { throw 'Unable to create temporary workspace alias' }
            $matrixMapping = @(& subst.exe) | Where-Object { $_.StartsWith($matrixDrive + '\:') }
            break
        }
    }
    if (!$matrixDrive) { throw 'No free temporary drive; run Python with an existing ASCII --temp-root' }
    $matrixTemporary = $matrixDrive + '/.runtime/matrix-tmp'
    New-Item -ItemType Directory -Path $matrixTemporary -Force | Out-Null
    $env:TEMP = $env:TMP = $matrixTemporary
    $matrixArguments = @('-B', (Join-Path $PSScriptRoot 'run_tia_matrix.py'),
        '--model', $Model, '--ids', $Ids, '--repeats', $Repeats, '--concurrency', $Concurrency,
        '--temp-root', $matrixTemporary)
    if ($PrepareOnly) { $matrixArguments += '--prepare-only' }
    & $matrixPython @matrixArguments
    $matrixExit = $LASTEXITCODE
} finally {
    $env:TEMP = $matrixOldTemp
    $env:TMP = $matrixOldTmp
    if ($matrixDrive -and $matrixMapping) {
        $matrixCurrentMapping = @(& subst.exe) | Where-Object { $_.StartsWith($matrixDrive + '\:') }
        if ($matrixCurrentMapping -eq $matrixMapping) { & subst.exe $matrixDrive /D }
    }
    Pop-Location
}
exit $matrixExit
