param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$ReviewAddress = "http://127.0.0.1:$Port"
$Health = Invoke-RestMethod -Uri "$ReviewAddress/api/health" -TimeoutSec 5
if ($Health.app -ne 'touchline-local-review') { throw 'This address is not the Touchline review app.' }
$ReviewSession = Invoke-RestMethod -Uri "$ReviewAddress/api/state" -TimeoutSec 10
Invoke-RestMethod -Method Post -Uri "$ReviewAddress/api/shutdown" -ContentType 'application/json' -Headers @{'X-Review-Token' = $ReviewSession.request_token} -Body '{}' -TimeoutSec 5 | Out-Null
Write-Host 'Local review server stopped.'
