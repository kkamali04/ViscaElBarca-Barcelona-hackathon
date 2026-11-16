param([string]$OutputFile = 'submissions/baseline_fallback.csv')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        throw 'Create .venv and install requirements-lock.txt first; see README.md.'
    }
    & $taskPython tools/build_baseline.py --out $OutputFile
    if ($LASTEXITCODE -ne 0) { throw 'Baseline generation failed.' }
    & $taskPython more-than-a-hack-2027-main/evaluation/validate_submission.py $OutputFile
    if ($LASTEXITCODE -ne 0) { throw 'Submission validation failed.' }
}
finally { Pop-Location }
