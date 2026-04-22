# Register daily Automation Tracker dashboard refresh at 7 AM.

$ErrorActionPreference = "Stop"

$TaskName   = "NSLS-Automation-Dashboard"
$PythonExe  = "C:\Users\apate\AppData\Local\Programs\Python\Python311\python.exe"
$ScriptPath = "C:\Users\apate\.claude\local-plugins\nsls-personal-toolkit\skills\automation-tracker-dashboard\scripts\refresh_dashboard.py"

$Action    = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`""
$Trigger   = New-ScheduledTaskTrigger -Daily -At 7:00AM
$Settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Refreshes Obsidian/AP/03-meta/automations-dashboard.md from the NSLS Automation Tracker API (read-only)." -Force

Write-Host "Scheduled task '$TaskName' registered. Runs daily at 7:00 AM." -ForegroundColor Green
