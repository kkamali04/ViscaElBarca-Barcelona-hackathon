param(
    [ValidateRange(1, 65535)][int]$Port = 8771,
    [string]$CacheDir = (Join-Path $PSScriptRoot 'local/replay-v2')
)
$ErrorActionPreference = 'Stop'
$ReplayAddress = "http://127.0.0.1:$Port"
$ReplayHealth = Invoke-RestMethod -Uri "$ReplayAddress/api/health" -TimeoutSec 5
if ($ReplayHealth.app -ne 'touchline-tracking-replay' -or $ReplayHealth.version -ne 2) {
    throw 'This address is not tracking replay v2.'
}
$ReplayStatePath = Join-Path $CacheDir "runtime-$Port.json"
$ReplayState = Get-Content -LiteralPath $ReplayStatePath -Raw | ConvertFrom-Json
if ($ReplayState.app -ne 'touchline-tracking-replay' -or $ReplayState.version -ne 2 -or $ReplayState.port -ne $Port -or -not $ReplayState.shutdown_token) {
    throw 'The private replay shutdown state is invalid.'
}
Invoke-RestMethod -Method Post -Uri "$ReplayAddress/api/shutdown" -ContentType 'application/json' -Headers @{'X-Replay-Token' = $ReplayState.shutdown_token} -Body '{}' -TimeoutSec 5 | Out-Null
Write-Host 'Local tracking replay server stopped.'
