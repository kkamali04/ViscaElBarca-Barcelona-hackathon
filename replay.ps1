param(
    [switch]$Demo,
    [string]$DataDir,
    [string]$Predictions,
    [string]$CacheDir,
    [ValidateRange(1, 65535)][int]$Port = 8771,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$ReplayPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $ReplayPython -PathType Leaf)) {
    throw 'Create the Python environment first, then install requirements-lock.txt as described in README.md.'
}
if ($Demo -and ($DataDir -or $Predictions)) { throw 'Demo mode cannot also select supplied tracking or predictions.' }
if (-not $Demo -and -not $DataDir) {
    $DataDir = Join-Path $PSScriptRoot 'more-than-a-hack-2027-main/data'
}
$ReplayArgs = @('-m', 'replay_v2', '--port', "$Port")
if ($Demo) { $ReplayArgs += '--demo' }
if ($DataDir) { $ReplayArgs += @('--data-dir', $DataDir) }
if ($Predictions) { $ReplayArgs += @('--predictions', $Predictions) }
if ($CacheDir) { $ReplayArgs += @('--cache-dir', $CacheDir) }
if (-not $NoBrowser) { $ReplayArgs += '--open' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $ReplayPython @ReplayArgs
    if ($LASTEXITCODE -ne 0) { throw "Replay exited with code $LASTEXITCODE. Check the selected mode, input root, port and cache permissions." }
} finally {
    Pop-Location
}
