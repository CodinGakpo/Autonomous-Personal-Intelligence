# Scheduled catch-up ingest for the mail knowledge-tree pipeline. Registered as a Windows
# Task Scheduler task (see SETUP.md) to run every 4 hours; the 240-minute window matches
# that cadence with no gap.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "brain\.cache"
$logFile = Join-Path $logDir "mail_cron.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Set-Location $repoRoot
& "$repoRoot\.venv\Scripts\python.exe" -m brain.mail_ingest run --since-minutes 240 *>> $logFile

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "[$timestamp] run finished with exit code $LASTEXITCODE"
