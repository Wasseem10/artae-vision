param(
  [Parameter(Mandatory = $true)]
  [string]$ApiProjectDirectory
)

$ErrorActionPreference = "Stop"

function New-UrlSafeKey {
  $bytes = [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
  # Keep the Base64 padding: Fernet requires the full 44-character URL-safe key.
  return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
}

function Set-ArtaeEnvironmentVariable {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$Value,
    [switch]$Sensitive
  )

  $sensitivityFlag = if ($Sensitive) { "--sensitive" } else { "--no-sensitive" }
  $null = $Value | & pnpm dlx vercel@latest env add $Name production --force --yes $sensitivityFlag 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to add Vercel environment variable: $Name"
  }
}

Push-Location -LiteralPath $ApiProjectDirectory
try {
  $settings = [ordered]@{
    VIDEO_INTEL_API_ENVIRONMENT = "production"
    VIDEO_INTEL_API_EDGE_AUTH_MODE = "device"
    VIDEO_INTEL_API_DASHBOARD_AUTH_MODE = "oidc"
    VIDEO_INTEL_API_OIDC_ISSUER = "https://zelkruekkwcyivuoqoal.supabase.co/auth/v1"
    VIDEO_INTEL_API_OIDC_AUDIENCE = "authenticated"
    VIDEO_INTEL_API_OIDC_JWKS_URL = "https://zelkruekkwcyivuoqoal.supabase.co/auth/v1/.well-known/jwks.json"
    VIDEO_INTEL_API_OIDC_ALGORITHMS = '["ES256"]'
    VIDEO_INTEL_API_OIDC_AUTO_PROVISION_MEMBERSHIPS = "true"
    VIDEO_INTEL_API_OIDC_AUTO_PROVISION_ORGANIZATIONS = "true"
    VIDEO_INTEL_API_HOST = "0.0.0.0"
    VIDEO_INTEL_API_CORS_ORIGINS = '["https://artae-vision.vercel.app"]'
    VIDEO_INTEL_API_MEDIA_GATEWAY_MODE = "disabled"
    VIDEO_INTEL_API_RECORDING_STORAGE_BACKEND = "supabase"
    VIDEO_INTEL_API_OBJECT_STORAGE_BUCKET = "artae-recordings"
    VIDEO_INTEL_API_OBJECT_STORAGE_PRESIGN_SECONDS = "300"
    VIDEO_INTEL_API_RECORDING_RETENTION_HOURS = "2"
    VIDEO_INTEL_API_RECORDING_UPLOAD_MAX_BYTES = "52428800"
    VIDEO_INTEL_API_RETENTION_POLICY_CONFIGURED = "true"
    VIDEO_INTEL_API_RULE_COMPILER_PROVIDER = "deterministic"
  }

  $secrets = [ordered]@{
    VIDEO_INTEL_API_AGENT_KEY = New-UrlSafeKey
    VIDEO_INTEL_API_DASHBOARD_KEY = New-UrlSafeKey
    VIDEO_INTEL_API_MEDIA_SIGNING_KEY = New-UrlSafeKey
    VIDEO_INTEL_API_ALERT_ENCRYPTION_KEY = New-UrlSafeKey
    VIDEO_INTEL_API_CAMERA_ENCRYPTION_KEY = New-UrlSafeKey
  }

  foreach ($entry in $settings.GetEnumerator()) {
    Set-ArtaeEnvironmentVariable -Name $entry.Key -Value ([string]$entry.Value)
  }

  foreach ($entry in $secrets.GetEnumerator()) {
    Set-ArtaeEnvironmentVariable -Name $entry.Key -Value ([string]$entry.Value) -Sensitive
  }

  Write-Output (
    "Configured {0} production variables. Supabase connection values remain managed by Vercel." -f (
      $settings.Count + $secrets.Count
    )
  )
}
finally {
  Pop-Location
}
