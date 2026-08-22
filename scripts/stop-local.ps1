$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workerPidFile = Join-Path $workspaceRoot ".runtime\worker.pid"
$composeFile = Join-Path $workspaceRoot "infra\docker-compose.yml"

if (Test-Path -LiteralPath $workerPidFile) {
    $savedPid = Get-Content -LiteralPath $workerPidFile | Select-Object -First 1
    if ($savedPid -match '^\d+$') {
        $worker = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" `
            -ErrorAction SilentlyContinue
        if ($null -ne $worker) {
            $expectedDirectory = (Join-Path $workspaceRoot ".venv\Scripts").ToLowerInvariant()
            $executablePath = ([string]$worker.ExecutablePath).ToLowerInvariant()
            if ($executablePath.StartsWith($expectedDirectory)) {
                Stop-Process -Id ([int]$savedPid) -Force
            }
        }
    }
    Remove-Item -LiteralPath $workerPidFile -Force
}

$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($null -ne $docker) {
    Set-Location -LiteralPath $workspaceRoot
    & $docker.Source compose -f $composeFile stop
}

Write-Host "Video Intelligence has stopped. Your database and saved evidence remain intact."
