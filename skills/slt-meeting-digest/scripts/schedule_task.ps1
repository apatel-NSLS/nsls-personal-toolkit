# Register a Windows Scheduled Task to poll Fathom + post SLT meeting digests every 15 minutes.
# Runs 24/7; the script self-deduplicates and self-rate-limits.

$ErrorActionPreference = "Stop"

$TaskName   = "NSLS-SLT-Meeting-Digest"
$PythonExe  = "C:\Users\apate\AppData\Local\Programs\Python\Python311\python.exe"
$ScriptPath = "C:\Users\apate\.claude\local-plugins\nsls-personal-toolkit\skills\slt-meeting-digest\scripts\poll_and_digest.py"

$Action    = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`""
$Trigger   = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
$Settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Polls Fathom every 15 min for SLT meetings; posts 3-bullet digests to Slack (or writes to Obsidian inbox fallback). Read-only against Fathom." -Force

Write-Host "Scheduled task '$TaskName' registered. Runs every 15 minutes." -ForegroundColor Green
Write-Host ""
Write-Host "Next step: set SLACK_BOT_TOKEN at ~/.claude/credentials/slt-meeting-digest.env" -ForegroundColor Yellow
Write-Host "  Until then, digests land in Obsidian/AP/00-inbox/slt-digest/ for manual review."
