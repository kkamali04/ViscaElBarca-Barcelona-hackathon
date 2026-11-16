param([switch]$Demo, [int]$Port = 8765, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$Python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Create the Python 3.13 environment first: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt'
}
$ReviewArgs = @('-m', 'review_app', '--port', "$Port")
if ($Demo) { $ReviewArgs += '--demo' }
if (-not $NoBrowser) { $ReviewArgs += '--open' }
& $Python @ReviewArgs
if ($LASTEXITCODE -ne 0) { throw "Review app exited with code $LASTEXITCODE. If the port is occupied, use -Port 8767." }
