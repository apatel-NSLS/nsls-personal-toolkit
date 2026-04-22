# Register a Windows Scheduled Task to generate the weekly brief every Sunday at 7 PM.

$ErrorActionPreference = "Stop"

$TaskName   = "NSLS-Weekly-Brief"
$PythonExe  = "C:\Users\apate\AppData\Local\Programs\Python\Python311\python.exe"
$ScriptPath = "C:\Users\apate\.claude\local-plugins\nsls-personal-toolkit\skills\weekly-brief\scripts\run_weekly_brief.py"

$Action    = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`""
$Trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 7:00PM
$Settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Generates weekly brief synthesizing the week's daily notes, Fathom meetings, and pre-meeting briefings. Output: Obsidian/AP/02-weekly/YYYY-WNN-brief.md" -Force

Write-Host "Scheduled task '$TaskName' registered. Runs Sundays at 7:00 PM." -ForegroundColor Green
