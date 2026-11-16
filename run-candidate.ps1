$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot/.venv/Scripts/python.exe" "$PSScriptRoot/tools/run_candidate.py" @args
if ($LASTEXITCODE -ne 0) { throw "Candidate run failed with exit code $LASTEXITCODE" }
