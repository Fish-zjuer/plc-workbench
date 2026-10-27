function Get-WorkbenchPython {
    param([Parameter(Mandatory=$true)][string]$ProjectRoot, [switch]$ProjectLocal)
    $localPython = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
    if ($ProjectLocal -or (Test-Path -LiteralPath $localPython)) { return $localPython }
    $candidateRoot = Get-Item -LiteralPath $ProjectRoot
    while ($candidateRoot) {
        $cachedPython = Join-Path $candidateRoot.FullName '_cache/plc-agent/venv/Scripts/python.exe'
        if (Test-Path -LiteralPath $cachedPython) { return $cachedPython }
        $candidateRoot = $candidateRoot.Parent
    }
    return $localPython
}
