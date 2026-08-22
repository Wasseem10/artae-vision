param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$DestinationDirectory
)

$ErrorActionPreference = "Stop"
$destination = [System.IO.Path]::GetFullPath($DestinationDirectory)
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

if ($DatabaseUrl.StartsWith("sqlite")) {
    $separator = $DatabaseUrl.IndexOf("///")
    if ($separator -lt 0) {
        throw "SQLite URL must contain an absolute or workspace-relative file path."
    }
    $sourceText = $DatabaseUrl.Substring($separator + 3)
    $source = [System.IO.Path]::GetFullPath($sourceText)
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "SQLite database was not found at $source"
    }
    $output = Join-Path $destination "control-plane-$timestamp.db"
    Copy-Item -LiteralPath $source -Destination $output
} elseif ($DatabaseUrl.StartsWith("postgresql")) {
    $pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
    if ($null -eq $pgDump) {
        throw "pg_dump is required for PostgreSQL backups. Install PostgreSQL client tools."
    }
    $output = Join-Path $destination "control-plane-$timestamp.dump"
    & $pgDump.Source --format=custom --file=$output $DatabaseUrl
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code $LASTEXITCODE"
    }
} else {
    throw "Only sqlite and postgresql database URLs are supported."
}

$resolvedOutput = [System.IO.Path]::GetFullPath($output)
if (-not $resolvedOutput.StartsWith($destination, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write outside the requested backup directory."
}
Write-Output $resolvedOutput
