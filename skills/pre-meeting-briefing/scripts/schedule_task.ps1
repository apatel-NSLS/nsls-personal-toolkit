# Register a Windows Scheduled Task to generate pre-meeting briefings daily at 6:00 AM.
# Run this script ONCE in PowerShell as the current user.

$ErrorActionPreference = "Stop"

$TaskName   = "NSLS-Pre-Meeting-Briefings"
$PythonExe  = "C:\Users\apate\AppData\Local\Programs\Python\Python311\python.exe"
$ScriptPath = "C:\Users\apate\.claude\local-plugins\nsls-personal-toolkit\skills\pre-meeting-briefing\scripts\run_briefings.py"

$Action    = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`" --today --tomorrow"
$Trigger   = New-ScheduledTaskTrigger -Daily -At 6:00AM
$Settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Generates pre-meeting briefings for SLT 1:1s using Fathom/Gmail/Slack/Obsidian data. Writes to 00-inbox/pre-meeting/. Part of Anish's NSLS builder toolkit." -Force

Write-Host ""
Write-Host "Scheduled task '$TaskName' registered." -ForegroundColor Green
Write-Host "Will run daily at 6:00 AM, generating briefings for today + tomorrow."
Write-Host ""
Write-Host "To run manually now:       Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To unregister:             Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:$false"
Write-Host "To view next run time:     Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
