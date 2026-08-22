[CmdletBinding()]
param(
    [string]$Rule,
    [ValidateSet("gemini", "dry_run")]
    [string]$Provider = "gemini",
    [ValidateRange(0, 20)]
    [int]$CameraIndex = 0
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$inferenceExecutable = Join-Path $workspace ".venv\Scripts\video-intelligence-inference.exe"
$environmentFile = Join-Path $workspace ".env"

$Host.UI.RawUI.WindowTitle = "AI Video Intelligence - Local Camera"
Set-Location -LiteralPath $workspace

if (-not (Test-Path -LiteralPath $inferenceExecutable)) {
    throw "The Python environment is missing. Expected: $inferenceExecutable"
}

if ($Provider -eq "gemini" -and -not (Test-Path -LiteralPath $environmentFile)) {
    throw "The .env file containing your Gemini API key is missing."
}

if ([string]::IsNullOrWhiteSpace($Rule)) {
    Write-Host ""
    Write-Host "AI Video Intelligence - Local Camera Playground" -ForegroundColor Cyan
    Write-Host "Type what the camera should alert you about." -ForegroundColor Gray
    Write-Host "Example: Alert me when someone is not wearing a hard hat." -ForegroundColor DarkGray
    Write-Host ""
    $Rule = Read-Host "Alert rule"
}

if ([string]::IsNullOrWhiteSpace($Rule)) {
    $Rule = "Alert me when someone is not wearing a hard hat."
}

$env:VIDEO_INTEL_CAMERA_INDEX = $CameraIndex.ToString()
$env:VIDEO_INTEL_OBSERVER_ENABLED = "true"
$env:VIDEO_INTEL_OBSERVER_PROVIDER = $Provider
$env:VIDEO_INTEL_OBSERVER_RULE = $Rule
$env:VIDEO_INTEL_OBSERVER_SHOW_SHEET = "false"
$env:VIDEO_INTEL_OBSERVER_ARTIFACT_MODE = "triggered"
$env:VIDEO_INTEL_WINDOW_TITLE = "AI Video Intelligence - press Q, Esc, or X to stop"

Write-Host ""
Write-Host "Starting camera..." -ForegroundColor Green
Write-Host "Rule: $Rule"
Write-Host "The first AI decision normally arrives after about 10 seconds." -ForegroundColor Gray
Write-Host "Triggered evidence is saved under artifacts\observer." -ForegroundColor Gray
Write-Host "Close the camera with Q, Esc, or the X button." -ForegroundColor Gray
Write-Host ""

& $inferenceExecutable
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "The camera stopped with an error. The message above explains what happened." -ForegroundColor Red
    Read-Host "Press Enter to close"
}

exit $exitCode
