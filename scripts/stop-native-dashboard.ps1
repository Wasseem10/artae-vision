$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $workspaceRoot ".runtime\native-dashboard-pids.json"
$apiBaseUrl = "http://127.0.0.1:8000/api/v1"
$localDashboardKey = "local-dashboard-key-development-only"
$allowedExecutables = @(
    (Join-Path $workspaceRoot ".venv\Scripts\video-intelligence-api.exe").ToLowerInvariant(),
    (Join-Path $workspaceRoot ".venv\Scripts\video-intelligence-worker.exe").ToLowerInvariant(),
    (Join-Path $workspaceRoot ".venv\Scripts\video-intelligence-alert-worker.exe").ToLowerInvariant()
)

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "The native dashboard is not running."
    exit 0
}

$saved = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json

# Persist the safe desired state before terminating the worker. This prevents a
# later local restart from resuming provider requests without an explicit click.
$dashboardHeaders = @{ "X-Dashboard-Key" = $localDashboardKey }
try {
    $cameras = @(Invoke-RestMethod -Uri "$apiBaseUrl/cameras" -Headers $dashboardHeaders -TimeoutSec 3)
    foreach ($camera in $cameras) {
        $stopBody = @{ desired_status = "stopped" } | ConvertTo-Json
        Invoke-RestMethod -Method Put -Uri "$apiBaseUrl/cameras/$($camera.id)/agent" `
            -Headers $dashboardHeaders -ContentType "application/json" -Body $stopBody `
            -TimeoutSec 3 | Out-Null
    }
    if ($cameras.Count -gt 0) {
        Write-Host "Camera analysis sessions placed in the safe stopped state." -ForegroundColor Yellow
        Start-Sleep -Milliseconds 750
    }
} catch {
    Write-Warning "Could not update camera state before shutdown: $($_.Exception.Message)"
}

foreach ($processId in @($saved.alertWorker, $saved.worker, $saved.web, $saved.api)) {
    if (-not $processId) { continue }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if ($null -eq $process) { continue }

    $executable = ([string]$process.ExecutablePath).ToLowerInvariant()
    $isWorkspaceService = $allowedExecutables -contains $executable
    $isNodeWeb = $executable.EndsWith("\node.exe") -and
        ([string]$process.CommandLine).Contains((Join-Path $workspaceRoot "apps\web"))
    if ($isWorkspaceService -or $isNodeWeb) {
        Stop-Process -Id ([int]$processId) -Force
    }
}

Remove-Item -LiteralPath $pidFile -Force
Write-Host "Native dashboard stopped. SQLite data and evidence were preserved."
