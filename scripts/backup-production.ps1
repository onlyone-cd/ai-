param(
  [string]$ComposeFile = "docker-compose.production.yml",
  [string]$EnvFile = ".env",
  [string]$BackupDir = "backups"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $BackupDir)) {
  New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dbFile = Join-Path $BackupDir "hireinsight-db-$timestamp.sql"
$uploadsFile = Join-Path $BackupDir "hireinsight-uploads-$timestamp.tar"
$manifestFile = Join-Path $BackupDir "hireinsight-backup-$timestamp.json"

docker compose -f $ComposeFile --env-file $EnvFile exec -T postgres pg_dump -U hireinsight -d hireinsight --clean --if-exists | Out-File -Encoding utf8 $dbFile

$appContainer = docker compose -f $ComposeFile --env-file $EnvFile ps -q app
if (!$appContainer) {
  throw "app container not found"
}
docker compose -f $ComposeFile --env-file $EnvFile exec -T app tar -C /data -cf /tmp/hireinsight-uploads-backup.tar uploads
docker cp "${appContainer}:/tmp/hireinsight-uploads-backup.tar" $uploadsFile
docker compose -f $ComposeFile --env-file $EnvFile exec -T app rm -f /tmp/hireinsight-uploads-backup.tar | Out-Null

$manifest = @{
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  database = (Resolve-Path $dbFile).Path
  uploads = (Resolve-Path $uploadsFile).Path
  compose_file = $ComposeFile
}
$manifest | ConvertTo-Json -Depth 3 | Out-File -Encoding utf8 $manifestFile

Write-Output "Backup complete:"
Write-Output "  Database: $dbFile"
Write-Output "  Uploads:  $uploadsFile"
Write-Output "  Manifest: $manifestFile"
