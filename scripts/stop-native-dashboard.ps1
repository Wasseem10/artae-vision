$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $workspaceRoot ".runtime\native-dashboard-pids.json"
$apiBaseUrl = "http://127.0.0.1:8000/api/v1"
$localDashboardKey = "local-dashboard-key-development-only"
$saved = if (Test-Path -LiteralPath $pidFile) {
    Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
} else {
    [pscustomobject]@{ api = $null; web = $null; worker = $null; alertWorker = $null }
}

function Test-WorkspaceServiceProcess($process) {
    $commandLine = [string]$process.CommandLine
    if ($commandLine.IndexOf($workspaceRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        return $false
    }
    return $commandLine.Contains("video_intelligence_api.main") -or
        $commandLine.Contains("video_intelligence_inference.worker") -or
        $commandLine.Contains("video_intelligence_alerts.worker") -or
        $commandLine.IndexOf((Join-Path $workspaceRoot "apps\web"), [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Stop-WorkspaceProcessTree([int]$rootProcessId, $allProcesses) {
    $root = $allProcesses | Where-Object { $_.ProcessId -eq $rootProcessId } | Select-Object -First 1
    if ($null -eq $root -or -not (Test-WorkspaceServiceProcess $root)) { return }
    $tree = [System.Collections.Generic.List[int]]::new()
    $pending = [System.Collections.Generic.Queue[int]]::new()
    $pending.Enqueue($rootProcessId)
    while ($pending.Count -gt 0) {
        $current = $pending.Dequeue()
        $tree.Add($current)
        foreach ($child in $allProcesses | Where-Object { $_.ParentProcessId -eq $current }) {
            $pending.Enqueue([int]$child.ProcessId)
        }
    }
    for ($index = $tree.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $tree[$index] -Force -ErrorAction SilentlyContinue
    }
}

# Persist the safe desired state before terminating the worker. This prevents a
# later local restart from resuming provider requests without an explicit click.
$dashboardHeaders = @{ "X-Dashboard-Key" = $localDashboardKey }
try {
    $cameraResponse = Invoke-RestMethod -Uri "$apiBaseUrl/cameras" `
        -Headers $dashboardHeaders -TimeoutSec 3
    foreach ($camera in $cameraResponse) {
        $stopBody = @{ desired_status = "stopped" } | ConvertTo-Json
        Invoke-RestMethod -Method Put -Uri "$apiBaseUrl/cameras/$($camera.id)/agent" `
            -Headers $dashboardHeaders -ContentType "application/json" -Body $stopBody `
            -TimeoutSec 3 | Out-Null
    }
    if (@($cameraResponse).Count -gt 0) {
        Write-Host "Camera analysis sessions placed in the safe stopped state." -ForegroundColor Yellow
        Start-Sleep -Milliseconds 750
    }
} catch {
    Write-Warning "Could not update camera state before shutdown: $($_.Exception.Message)"
}

$allProcesses = @(Get-CimInstance Win32_Process)
$workspaceRoots = @($allProcesses | Where-Object { Test-WorkspaceServiceProcess $_ })
foreach ($process in $workspaceRoots) {
    $parentIsWorkspaceService = $workspaceRoots | Where-Object { $_.ProcessId -eq $process.ParentProcessId } | Select-Object -First 1
    if ($null -eq $parentIsWorkspaceService) {
        Stop-WorkspaceProcessTree ([int]$process.ProcessId) $allProcesses
    }
}

if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force }
Write-Host "Native dashboard stopped. SQLite data and evidence were preserved."
