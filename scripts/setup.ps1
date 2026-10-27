param([switch]$CheckOnly, [switch]$ProjectLocal)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime-path.ps1')
$runtimePython = Get-WorkbenchPython -ProjectRoot $projectRoot -ProjectLocal:$ProjectLocal
$environmentRoot = Split-Path -Parent (Split-Path -Parent $runtimePython)
if ($CheckOnly) {
    if (!(Test-Path -LiteralPath $runtimePython)) { throw 'Runtime missing; run scripts/setup.ps1' }
    & $runtimePython -c 'import textual,pypdf; print(textual.__version__,pypdf.__version__)'
    exit $LASTEXITCODE
}
if (!(Test-Path -LiteralPath $runtimePython)) {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonCommand) { $pythonExecutable = $pythonCommand.Source; $pythonArguments = @('-3') }
    else { $pythonExecutable = (Get-Command python -ErrorAction Stop).Source; $pythonArguments = @() }
    & $pythonExecutable @pythonArguments -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required; install Python and reopen the terminal.' }
    & $pythonExecutable @pythonArguments -m venv $environmentRoot
    if ($LASTEXITCODE -ne 0) { throw 'Creating Python 3.10+ environment failed' }
}
$wheelRoot = Join-Path $projectRoot '.runtime/wheels'
New-Item -ItemType Directory -Path $wheelRoot -Force | Out-Null
$packages = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dependencies.json') -Raw | ConvertFrom-Json
foreach ($package in $packages) {
    if ($package.url -notlike 'https://files.pythonhosted.org/*') { throw 'Unexpected wheel source' }
    $wheel = Join-Path $wheelRoot $package.filename
    $bundledWheel = Join-Path $projectRoot ('vendor/wheels/' + $package.filename)
    if (!(Test-Path -LiteralPath $wheel) -and (Test-Path -LiteralPath $bundledWheel)) { Copy-Item -LiteralPath $bundledWheel -Destination $wheel }
    if (!(Test-Path -LiteralPath $wheel)) {
        Write-Host "Downloading $($package.name) $($package.version)"
        Invoke-WebRequest -Uri $package.url -OutFile $wheel -TimeoutSec 60
    }
    $hashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
    $hashStream = [System.IO.File]::OpenRead($wheel)
    try { $actualHash = [System.BitConverter]::ToString($hashAlgorithm.ComputeHash($hashStream)).Replace('-', '').ToLowerInvariant() }
    finally { $hashStream.Dispose(); $hashAlgorithm.Dispose() }
    if ($actualHash -ne $package.sha256) { throw "Digest mismatch: $($package.name)" }
}
& $runtimePython -m pip install --no-index --find-links $wheelRoot --require-hashes -r (Join-Path $projectRoot 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
Write-Host 'Ready. Start using launch.cmd.'
