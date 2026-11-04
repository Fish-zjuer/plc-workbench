param(
    [switch]$Acknowledge,
    [ValidateRange(1, 86400)][int]$TimeoutSeconds = 1800,
    [ValidateRange(1, 1000)][int]$MaxClicks = 10
)
$ErrorActionPreference = 'Stop'
$trialRepoRoot = Split-Path -Parent $PSScriptRoot
$trialExecutable = Join-Path $trialRepoRoot 'integrations\tia_trial_ack\bin\Release\net48\TiaTrialAck.exe'
if (-not (Test-Path -LiteralPath $trialExecutable)) {
    $trialProject = Join-Path $trialRepoRoot 'integrations\tia_trial_ack\TiaTrialAck.csproj'
    & dotnet build $trialProject -c Release --nologo
    if ($LASTEXITCODE -ne 0) { throw 'Trial notice watcher build failed.' }
}
$trialLogRoot = Join-Path $trialRepoRoot 'outputs\trial_ack'
New-Item -ItemType Directory -Path $trialLogRoot -Force | Out-Null
$trialRunId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8)
$trialStdout = Join-Path $trialLogRoot ($trialRunId + '.out.log')
$trialStderr = Join-Path $trialLogRoot ($trialRunId + '.err.log')
$trialArguments = @('--timeout-seconds', "$TimeoutSeconds", '--max-clicks', "$MaxClicks")
if ($Acknowledge) { $trialArguments += '--ack-trial-notice' }
$trialWatcher = Start-Process -FilePath $trialExecutable -ArgumentList $trialArguments `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $trialStdout -RedirectStandardError $trialStderr
[pscustomobject]@{
    ProcessId = $trialWatcher.Id
    Mode = $(if ($Acknowledge) { 'Acknowledge matching trial reminder only' } else { 'Observe only; no clicks' })
    TimeoutSeconds = $TimeoutSeconds
    MaximumAcknowledgements = $MaxClicks
    OutputLog = $trialStdout
    ErrorLog = $trialStderr
}
