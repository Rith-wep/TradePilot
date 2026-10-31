param([switch]$Keep)
$ErrorActionPreference = "Stop"

function Invoke-Docker([string[]]$DockerArgs) {
  & docker @DockerArgs
  if ($LASTEXITCODE -ne 0) { throw "docker command failed: docker $($DockerArgs -join ' ')" }
}

$serverRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $serverRoot "..")).Path
$runRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("tradepilot-docker-" + [guid]::NewGuid().ToString("N"))
$dataRoot = Join-Path $runRoot "data"
$reportRoot = Join-Path $runRoot "reports"
$secretRoot = Join-Path $runRoot "secrets"
New-Item -ItemType Directory -Force $dataRoot, $reportRoot, $secretRoot | Out-Null

$revision = (git -C $repoRoot rev-parse HEAD).Trim()
if ($revision -notmatch '^[0-9a-f]{40}$') { throw "A full Git revision is required." }
$env:TRADEPILOT_IMPLEMENTATION_REVISION = $revision
$env:TRADEPILOT_DATA_HOST_PATH = $dataRoot
$env:TRADEPILOT_REPORT_HOST_PATH = $reportRoot
$env:OIDC_ISSUER = "https://oidc:8443"
$env:OIDC_AUDIENCE = "tradepilot-api"
$env:OIDC_JWKS_URL = "https://oidc:8443/.well-known/jwks.json"
foreach ($role in @("admin", "migrator", "api", "worker")) {
  $path = Join-Path $secretRoot ("postgres_{0}_password.txt" -f $role)
  [System.IO.File]::WriteAllText($path, ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")))
  Set-Item -Path ("env:POSTGRES_{0}_PASSWORD_FILE" -f $role.ToUpperInvariant()) -Value $path
}

$compose = @("compose", "-f", "compose.yaml", "-f", "compose.integration.yaml")
Push-Location $serverRoot
try {
  Invoke-Docker ($compose + @("build", "api", "worker", "smoke", "oidc"))
  Invoke-Docker ($compose + @("up", "-d", "postgres", "migrations", "oidc", "api"))
  Invoke-Docker ($compose + @("run", "--rm", "smoke", "worker", "node", "dist/src/docker/smoke.js", "seed-submit"))

  Invoke-Docker ($compose + @("up", "-d", "worker"))
  Invoke-Docker ($compose + @("run", "--rm", "smoke", "worker", "node", "dist/src/docker/smoke.js", "wait-running"))

  Invoke-Docker ($compose + @("pause", "worker"))
  Start-Sleep -Seconds 6
  Invoke-Docker ($compose + @("kill", "worker"))
  Invoke-Docker ($compose + @("rm", "-f", "worker"))
  Invoke-Docker ($compose + @("up", "-d", "worker"))
  Invoke-Docker ($compose + @("run", "--rm", "smoke", "worker", "node", "dist/src/docker/smoke.js", "verify"))
  Invoke-Docker ($compose + @("ps"))
} finally {
  if (-not $Keep) { & docker @compose down -v --remove-orphans }
  Pop-Location
  if (-not $Keep) { Remove-Item -LiteralPath $runRoot -Recurse -Force }
}
