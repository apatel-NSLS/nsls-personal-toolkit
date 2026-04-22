# Register a Windows Scheduled Task to refresh the Board Tasks dashboard daily at 7:05 AM.
# Run this script ONCE in PowerShell.

$ErrorActionPreference = "Stop"

$TaskName   = "NSLS-Board-Tasks"
$PythonExe  = "C:\Users\apate\AppData\Local\Programs\Python\Python311\python.exe"
$ScriptPath = "C:\Users\apate\.claude\local-plugins\nsls-personal-toolkit\skills\board-tasks-tracker\scripts\refresh_board_tasks.py"

$Action    = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`""
$Trigger   = New-ScheduledTaskTrigger -Daily -At 7:05AM
$Settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Refreshes Obsidian/AP/03-meta/board-tasks.md from the SLT Meeting Intelligence Airtable base. Read-only." -Force

Write-Host "Scheduled task '$TaskName' registered. Runs daily at 7:05 AM." -ForegroundColor Green
