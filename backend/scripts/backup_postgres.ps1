param(
    [string]$BackupDir = ".\backups",
    [int]$RetentionDays = 14,
    [string]$DatabaseUrl = ""
)

$ErrorActionPreference = "Stop"

function Get-DatabaseUrl {
    param([string]$ExplicitUrl)

    if ($ExplicitUrl) {
        return $ExplicitUrl
    }

    if ($env:DATABASE_URL) {
        return $env:DATABASE_URL
    }

    $envFile = Join-Path (Resolve-Path -LiteralPath ".") ".env"
    if (Test-Path -LiteralPath $envFile) {
        $line = Get-Content -LiteralPath $envFile |
            Where-Object { $_ -match '^DATABASE_URL=' } |
            Select-Object -First 1
        if ($line) {
            return ($line -replace '^DATABASE_URL=', '').Trim()
        }
    }

    throw "DATABASE_URL is not set and was not found in .env"
}

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    throw "pg_dump was not found in PATH"
}

$resolvedDatabaseUrl = Get-DatabaseUrl -ExplicitUrl $DatabaseUrl

$targetDir = Resolve-Path -LiteralPath "." | ForEach-Object {
    Join-Path $_ $BackupDir
}

if (-not (Test-Path -LiteralPath $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpPath = Join-Path $targetDir "timewise-$timestamp.dump"

& pg_dump --format=custom --file="$dumpPath" "$resolvedDatabaseUrl"

Get-ChildItem -LiteralPath $targetDir -File |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
    Remove-Item -Force

Write-Host "Backup created: $dumpPath"
