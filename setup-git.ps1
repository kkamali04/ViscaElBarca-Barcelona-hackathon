# Run once in each clone; changes only this repository's local Git settings.
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$TeamIgnore = (Resolve-Path -LiteralPath (Join-Path $RepoRoot '.gitignore.team')).Path
$GitExe = (Get-Command git.exe -ErrorAction Stop).Source
function Set-RepoConfig([string]$Name, [string]$Value) {
    & $GitExe -C $RepoRoot config --local $Name $Value
    if ($LASTEXITCODE -ne 0) { throw "Could not configure $Name" }
}
Set-RepoConfig 'core.excludesFile' $TeamIgnore
Set-RepoConfig 'core.autocrlf' 'false'
Set-RepoConfig 'core.hooksPath' '.githooks'
Set-RepoConfig 'pull.ff' 'only'
Set-RepoConfig 'pull.rebase' 'false'
Write-Host 'Configured repository-local privacy exclusions, exact bytes, size hooks and fast-forward pulls.'
