$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDirectory = Join-Path $workspaceRoot ".runtime"
$apiExecutable = Join-Path $workspaceRoot ".venv\Scripts\video-intelligence-api.exe"
$workerExecutable = Join-Path $workspaceRoot ".venv\Scripts\video-intelligence-worker.exe"
$alertWorkerExecutable = Join-Path $workspaceRoot ".venv\Scripts\video-intelligence-alert-worker.exe"
$alembicExecutable = Join-Path $workspaceRoot ".venv\Scripts\alembic.exe"
$webDirectory = Join-Path $workspaceRoot "apps\web"
$nextScript = Join-Path $webDirectory "node_modules\next\dist\bin\next"
$databasePath = Join-Path $runtimeDirectory "native-control-plane.db"
$pidFile = Join-Path $runtimeDirectory "native-dashboard-pids.json"
$dashboardUrl = "http://127.0.0.1:3000"
$apiBaseUrl = "http://127.0.0.1:8000/api/v1"
$apiHealthUrl = "http://127.0.0.1:8000/api/v1/health/live"

$localAgentKey = "local-agent-key-development-only"
$localDashboardKey = "local-dashboard-key-development-only"

foreach ($required in @($apiExecutable, $workerExecutable, $alertWorkerExecutable, $alembicExecutable, $nextScript)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "A required local dependency is missing: $required"
    }
}

$node = Get-Command node.exe -ErrorAction SilentlyContinue
if ($null -eq $node) {
    $bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
    if (Test-Path -LiteralPath $bundledNode) {
        $nodePath = $bundledNode
    } else {
        throw "Node.js is not installed or is not available on PATH."
    }
} else {
    $nodePath = $node.Source
}

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
Set-Location -LiteralPath $workspaceRoot

if (Test-Path -LiteralPath $pidFile) {
    $existing = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $live = @($existing.api, $existing.web, $existing.worker, $existing.alertWorker) | Where-Object {
        $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue)
    }
    if ($live.Count -gt 0) {
        Start-Process $dashboardUrl
        Write-Host "The native dashboard is already running at $dashboardUrl" -ForegroundColor Green
        exit 0
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$databaseUrl = "sqlite+aiosqlite:///" + $databasePath.Replace("\", "/")
$env:VIDEO_INTEL_API_DATABASE_URL = $databaseUrl
$env:VIDEO_INTEL_API_AGENT_KEY = $localAgentKey
$env:VIDEO_INTEL_API_DASHBOARD_KEY = $localDashboardKey
$env:VIDEO_INTEL_API_MEDIA_SIGNING_KEY = "local-media-signing-key-development-only-1234"
$env:VIDEO_INTEL_API_ALERT_ENCRYPTION_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
$env:VIDEO_INTEL_API_MEDIA_GATEWAY_MODE = "disabled"
$env:VIDEO_INTEL_API_REPLAY_DIRECTORY = (Join-Path $runtimeDirectory "replays")
$env:VIDEO_INTEL_API_RULE_COMPILER_PROVIDER = "deterministic"
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
$env:NEXT_PUBLIC_DASHBOARD_KEY = $localDashboardKey
$env:NEXT_PUBLIC_DEPLOYMENT_MODE = "native"
$env:VIDEO_INTEL_CONTROL_PLANE_URL = "http://127.0.0.1:8000"
$env:VIDEO_INTEL_CONTROL_PLANE_AGENT_KEY = $localAgentKey
$env:VIDEO_INTEL_WORKER_ID = "native-windows-worker"
$env:VIDEO_INTEL_ALERT_CONTROL_PLANE_URL = "http://127.0.0.1:8000"
$env:VIDEO_INTEL_ALERT_AGENT_KEY = $localAgentKey
$env:VIDEO_INTEL_ALERT_WORKER_ID = "native-windows-alert-worker"

Write-Host "Preparing the local SQLite database..." -ForegroundColor Cyan
& $alembicExecutable -c (Join-Path $workspaceRoot "services\api\alembic.ini") upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed."
}

$apiOut = Join-Path $runtimeDirectory "native-api.log"
$apiErr = Join-Path $runtimeDirectory "native-api-error.log"
$webOut = Join-Path $runtimeDirectory "native-web.log"
$webErr = Join-Path $runtimeDirectory "native-web-error.log"
$workerOut = Join-Path $runtimeDirectory "native-worker.log"
$workerErr = Join-Path $runtimeDirectory "native-worker-error.log"
$alertWorkerOut = Join-Path $runtimeDirectory "native-alert-worker.log"
$alertWorkerErr = Join-Path $runtimeDirectory "native-alert-worker-error.log"

$api = Start-Process -FilePath $apiExecutable -PassThru -WindowStyle Hidden `
    -WorkingDirectory $workspaceRoot -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr

$apiReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri $apiHealthUrl -TimeoutSec 2
        if ($health.status -eq "ok") {
            $apiReady = $true
            break
        }
    } catch {
        if ($api.HasExited) { break }
    }
}
if (-not $apiReady) {
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    throw "The native API did not start. See $apiErr"
}

# A local process restart must never silently resume paid visual analysis. The
# operator explicitly starts each camera session from the dashboard instead.
$dashboardHeaders = @{ "X-Dashboard-Key" = $localDashboardKey }
try {
    $cameras = @(Invoke-RestMethod -Uri "$apiBaseUrl/cameras" -Headers $dashboardHeaders -TimeoutSec 5)
    foreach ($camera in $cameras) {
        $stopBody = @{ desired_status = "stopped" } | ConvertTo-Json
        Invoke-RestMethod -Method Put -Uri "$apiBaseUrl/cameras/$($camera.id)/agent" `
            -Headers $dashboardHeaders -ContentType "application/json" -Body $stopBody `
            -TimeoutSec 5 | Out-Null
    }
    if ($cameras.Count -gt 0) {
        Write-Host "Local safety: all camera analysis sessions start stopped." -ForegroundColor Yellow
    }
} catch {
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    throw "Could not place cameras in the safe stopped state: $($_.Exception.Message)"
}

$quotedNextScript = '"' + $nextScript + '"'
$web = Start-Process -FilePath $nodePath -ArgumentList @($quotedNextScript, "dev", "--hostname", "127.0.0.1") `
    -PassThru -WindowStyle Hidden -WorkingDirectory $webDirectory `
    -RedirectStandardOutput $webOut -RedirectStandardError $webErr

$worker = Start-Process -FilePath $workerExecutable -PassThru -WindowStyle Hidden `
    -WorkingDirectory $workspaceRoot -RedirectStandardOutput $workerOut `
    -RedirectStandardError $workerErr

$alertWorker = Start-Process -FilePath $alertWorkerExecutable -PassThru -WindowStyle Hidden `
    -WorkingDirectory $workspaceRoot -RedirectStandardOutput $alertWorkerOut `
    -RedirectStandardError $alertWorkerErr

@{ api = $api.Id; web = $web.Id; worker = $worker.Id; alertWorker = $alertWorker.Id } |
    ConvertTo-Json |
    Set-Content -LiteralPath $pidFile -Encoding UTF8

$webReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -Uri $dashboardUrl -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $webReady = $true
            break
        }
    } catch {
        if ($web.HasExited) { break }
    }
}
if (-not $webReady) {
    foreach ($startedProcess in @($alertWorker, $worker, $web, $api)) {
        if ($null -ne $startedProcess -and -not $startedProcess.HasExited) {
            Stop-Process -Id $startedProcess.Id -Force
        }
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    throw "The native web dashboard did not start. See $webErr"
}

Start-Process $dashboardUrl
Write-Host "Native dashboard started at $dashboardUrl" -ForegroundColor Green
Write-Host "SQLite data: $databasePath" -ForegroundColor Gray
Write-Host "Use Stop-Native-Dashboard.cmd when you are finished." -ForegroundColor Gray
