[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DataDir,
    [ValidateRange(1024,65535)][int]$Port = 8771,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Set up Python 3.13 and requirements-lock.txt as shown in README.md first.'
}
$InputRoot = (Resolve-Path -LiteralPath $DataDir -ErrorAction Stop).Path
foreach ($Name in @('BAR-ATH_tactical_atd.xml','BAR-ATH_tactical_atd.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $InputRoot "tactical\$Name") -PathType Leaf)) {
        throw 'Choose the challenge data directory containing tactical ATD XML and TXT files.'
    }
}
# Fail before a full inference run when the selected port is already occupied.
$Probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
try { $Probe.Start() }
catch { throw "Port $Port is in use. Choose another -Port or stop that viewer first." }
finally { $Probe.Stop() }

$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$RunRoot = Join-Path $ProjectRoot "local\match-runs\$RunId"
# Outputs never live inside supplied inputs, even if an unsuitable input root was selected.
$ResolvedRunRoot = [System.IO.Path]::GetFullPath($RunRoot)
$InputPrefix = $InputRoot.TrimEnd('\','/') + [System.IO.Path]::DirectorySeparatorChar
if ($ResolvedRunRoot.Equals($InputRoot,[System.StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedRunRoot.StartsWith($InputPrefix,[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose an input data directory separate from the project local output directory.'
}
New-Item -ItemType Directory -Path $RunRoot | Out-Null
$Csv = Join-Path $RunRoot 'candidate.csv'
$Report = Join-Path $RunRoot 'candidate-run.json'
Write-Host 'Step 1/2: generate per-frame possession predictions from supplied ATD tracking.'
& $Python (Join-Path $ProjectRoot 'tools\run_candidate.py') --data-dir $InputRoot --no-cache --out $Csv --report $Report
if ($LASTEXITCODE -ne 0) { throw "Inference failed with exit code $LASTEXITCODE. The replay was not started." }
Write-Host "Prediction CSV and run report: $RunRoot"
Write-Host "Step 2/2: open supplied tracking with the generated prediction overlay at http://127.0.0.1:$Port/"
$ReplayArgs = @{ DataDir=$InputRoot; Predictions=$Csv; Port=$Port; CacheDir=(Join-Path $ProjectRoot 'local\replay-v2') }
if ($NoBrowser) { $ReplayArgs.NoBrowser = $true }
& (Join-Path $ProjectRoot 'replay.ps1') @ReplayArgs
