$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $workspaceRoot "infra\docker-compose.yml"
$environmentFile = Join-Path $workspaceRoot ".env"
$workerExecutable = Join-Path $workspaceRoot ".venv\Scripts\video-intelligence-worker.exe"
$runtimeDirectory = Join-Path $workspaceRoot ".runtime"
$logDirectory = Join-Path $workspaceRoot "artifacts\logs"
$workerPidFile = Join-Path $runtimeDirectory "worker.pid"

function Get-DotEnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Test-Path -LiteralPath $environmentFile)) {
        return $null
    }
    $prefix = "$Name="
    $line = Get-Content -LiteralPath $environmentFile |
        Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) } |
        Select-Object -Last 1
    if ($null -eq $line) {
        return $null
    }
    return $line.Substring($prefix.Length).Trim().Trim('"').Trim("'")
}

if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw "The private .env file is missing. Copy .env.example to .env first."
}
if (-not (Test-Path -LiteralPath $workerExecutable)) {
    throw "The Python workspace is not installed. Run the installation commands in README.md."
}

$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    throw "Docker Desktop is not installed. Install it from https://www.docker.com/products/docker-desktop/ and run this launcher again."
}

New-Item -ItemType Directory -Force -Path $runtimeDirectory, $logDirectory | Out-Null
Set-Location -LiteralPath $workspaceRoot

& $docker.Source info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "Docker is installed but is not running. Start Docker Desktop and try again."
    }
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    $dockerReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 2
        & $docker.Source info *> $null
        if ($LASTEXITCODE -eq 0) {
            $dockerReady = $true
            break
        }
    }
    if (-not $dockerReady) {
        throw "Docker Desktop did not become ready within two minutes."
    }
}

Write-Host "Starting the dashboard, API, database, media gateway, and alert worker..."
& $docker.Source compose -f $composeFile up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not start the local platform."
}

$apiReady = $false
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 `
            -Uri "http://127.0.0.1:8000/api/v1/health/ready"
        if ($response.StatusCode -eq 200) {
            $apiReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $apiReady) {
    throw "The API did not become ready within three minutes."
}

$existingWorker = $null
if (Test-Path -LiteralPath $workerPidFile) {
    $savedPid = Get-Content -LiteralPath $workerPidFile | Select-Object -First 1
    if ($savedPid -match '^\d+$') {
        $existingWorker = Get-Process -Id ([int]$savedPid) -ErrorAction SilentlyContinue
    }
}

if ($null -eq $existingWorker) {
    $apiAgentKey = Get-DotEnvValue -Name "VIDEO_INTEL_API_AGENT_KEY"
    if ([string]::IsNullOrWhiteSpace($apiAgentKey)) {
        $apiAgentKey = "local-agent-key-change-me"
    }
    $env:VIDEO_INTEL_CONTROL_PLANE_URL = "http://127.0.0.1:8000"
    $env:VIDEO_INTEL_CONTROL_PLANE_AGENT_KEY = $apiAgentKey
    $env:VIDEO_INTEL_WORKER_ID = "local-windows-worker"
    $env:VIDEO_INTEL_WORKER_MAX_CAMERAS = "1"

    $worker = Start-Process -FilePath $workerExecutable `
        -WorkingDirectory $workspaceRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "worker.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "worker.err.log") `
        -PassThru
    Set-Content -LiteralPath $workerPidFile -Value $worker.Id -Encoding ascii
}

Start-Process "http://127.0.0.1:3000"
Write-Host "Video Intelligence is ready at http://127.0.0.1:3000"
Write-Host "Use Stop-Video-Intelligence.cmd when you are finished."
