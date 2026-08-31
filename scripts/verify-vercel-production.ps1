param(
  [Parameter(Mandatory = $true)]
  [string]$ApiProjectDirectory
)

$ErrorActionPreference = "Stop"
$pythonPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe")).Path
$temporaryPath = Join-Path (
  [IO.Path]::GetTempPath()
) ("artae-verify-" + [guid]::NewGuid().ToString("N") + ".env")
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())

Push-Location -LiteralPath $ApiProjectDirectory
try {
  $null = & pnpm dlx vercel@latest env pull $temporaryPath --environment=production --yes 2>&1
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $temporaryPath)) {
    throw "Could not pull Vercel production environment variables."
  }

  $environmentArguments = @()
  foreach ($line in Get-Content -LiteralPath $temporaryPath) {
    if ($line -match "^(?<name>[A-Za-z_][A-Za-z0-9_]*)=(?<value>.*)$") {
      $value = $Matches["value"].Trim()
      if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
        $value = $value | ConvertFrom-Json
      }
      Set-Item -LiteralPath ("Env:" + $Matches["name"]) -Value ([string]$value)
      $environmentArguments += $Matches["name"]
    }
  }

  Write-Output ("CORS configuration: " + $env:VIDEO_INTEL_API_CORS_ORIGINS)

  & $pythonPath -c "from api.index import app; print(app.title)"
  if ($LASTEXITCODE -ne 0) {
    throw "The API failed to start with the Vercel production environment."
  }

  foreach ($environmentName in $environmentArguments) {
    Remove-Item -LiteralPath ("Env:" + $environmentName) -ErrorAction SilentlyContinue
  }
}
finally {
  Pop-Location
  if (Test-Path -LiteralPath $temporaryPath) {
    $resolvedDeletePath = (Resolve-Path -LiteralPath $temporaryPath).Path
    if ($resolvedDeletePath.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
      Remove-Item -LiteralPath $resolvedDeletePath -Force
    }
  }
}
