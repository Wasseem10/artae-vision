param(
  [Parameter(Mandatory = $true)]
  [string]$ApiProjectDirectory,
  [Parameter(Mandatory = $true)]
  [string]$WebProjectDirectory
)

$ErrorActionPreference = "Stop"
$temporaryPath = Join-Path (
  [IO.Path]::GetTempPath()
) ("artae-public-" + [guid]::NewGuid().ToString("N") + ".env")
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())

try {
  Push-Location -LiteralPath $ApiProjectDirectory
  try {
    $null = & pnpm dlx vercel@latest env pull $temporaryPath --environment=production --yes 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "Could not read the API project's Vercel integration variables."
    }
  }
  finally {
    Pop-Location
  }

  $variables = @{}
  foreach ($line in Get-Content -LiteralPath $temporaryPath) {
    if ($line -match "^(?<name>[A-Za-z_][A-Za-z0-9_]*)=(?<value>.*)$") {
      $value = $Matches["value"].Trim()
      if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
        $value = $value | ConvertFrom-Json
      }
      $variables[$Matches["name"]] = [string]$value
    }
  }

  $supabaseUrl = $variables["NEXT_PUBLIC_SUPABASE_URL"]
  if ([string]::IsNullOrWhiteSpace($supabaseUrl)) {
    $supabaseUrl = $variables["SUPABASE_URL"]
  }
  $publishableKey = $variables["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]
  if ([string]::IsNullOrWhiteSpace($publishableKey)) {
    $publishableKey = $variables["SUPABASE_PUBLISHABLE_KEY"]
  }

  foreach ($value in @($supabaseUrl, $publishableKey)) {
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq "[SENSITIVE]") {
      throw "The Supabase integration did not expose usable public browser values."
    }
  }

  Push-Location -LiteralPath $WebProjectDirectory
  try {
    $null = & pnpm dlx vercel@latest env add NEXT_PUBLIC_SUPABASE_URL `
      production,preview,development --force --yes --no-sensitive --value $supabaseUrl 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "Could not configure the frontend Supabase URL."
    }
    $null = & pnpm dlx vercel@latest env add NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY `
      production,preview,development --force --yes --no-sensitive --value $publishableKey 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "Could not configure the frontend Supabase publishable key."
    }
  }
  finally {
    Pop-Location
  }

  $response = Invoke-WebRequest `
    -Uri ($supabaseUrl + "/auth/v1/settings") `
    -Headers @{ apikey = $publishableKey } `
    -TimeoutSec 20 `
    -UseBasicParsing
  $authSettings = $response.Content | ConvertFrom-Json
  Write-Output ("Artae authentication endpoint status: {0}" -f [int]$response.StatusCode)
  Write-Output ("Google provider enabled: {0}" -f [bool]$authSettings.external.google)
}
finally {
  if (Test-Path -LiteralPath $temporaryPath) {
    $resolvedPath = (Resolve-Path -LiteralPath $temporaryPath).Path
    if ($resolvedPath.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
      Remove-Item -LiteralPath $resolvedPath -Force
    }
  }
}
