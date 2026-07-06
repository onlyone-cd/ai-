param(
  [Parameter(Mandatory = $true)][string]$DatabaseBackup,
  [Parameter(Mandatory = $true)][string]$UploadsBackup,
  [string]$ComposeFile = "docker-compose.production.yml",
  [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $DatabaseBackup)) {
  throw "Database backup not found: $DatabaseBackup"
}
if (!(Test-Path $UploadsBackup)) {
  throw "Uploads backup not found: $UploadsBackup"
}

Write-Output "This will restore production database and uploads from backups."
$confirm = Read-Host "Type RESTORE to continue"
if ($confirm -ne "RESTORE") {
  throw "Restore cancelled"
}

Get-Content -Raw $DatabaseBackup | docker compose -f $ComposeFile --env-file $EnvFile exec -T postgres psql -U hireinsight -d hireinsight

$appContainer = docker compose -f $ComposeFile --env-file $EnvFile ps -q app
if (!$appContainer) {
  throw "app container not found"
}
docker cp $UploadsBackup "${appContainer}:/tmp/hireinsight-uploads-restore.tar"
docker compose -f $ComposeFile --env-file $EnvFile exec -T app sh -c "rm -rf /data/uploads && tar -C /data -xf /tmp/hireinsight-uploads-restore.tar && rm -f /tmp/hireinsight-uploads-restore.tar"

Write-Output "Restore complete."
