# Shared runner for scheduled Claude Code rituals (open-day, close-day, open-week, close-week).
# Invoked by Task Scheduler with -Ritual <name>. Runs claude headless, logs output, captures exit code.
# NOTE: Headless mode does not parse slash commands. We invoke the skill by name in prose instead.

param(
  [Parameter(Mandatory=$true)][ValidateSet("open-day","close-day","open-week","close-week")]
  [string]$Ritual
)

$ErrorActionPreference = "Continue"

$ClaudeBin   = "C:\Users\apate\.local\bin\claude.exe"
$WorkingDir  = "C:\Users\apate\OneDrive\Desktop\Claude AI"
$LogRoot     = "C:\Users\apate\.claude\local-plugins\nsls-personal-toolkit\scripts\scheduled\logs"

$null = New-Item -ItemType Directory -Path $LogRoot -Force

$Stamp   = Get-Date -Format "yyyy-MM-dd"
$LogFile = Join-Path $LogRoot ("{0}-{1}.log" -f $Ritual, $Stamp)

Set-Location $WorkingDir

# Per-ritual prompts. Each tells Claude to invoke the named skill and run non-interactively.
$Prompts = @{
  "open-day"   = "Invoke the open-day skill from the nsls-personal-toolkit and run it non-interactively for today. Pull Gmail invites, Airtable tasks, yesterday's carry-overs, and any AI seeds. For meetings: if Google Calendar / Gmail MCP tools aren't loaded in this headless session, USE THE IMAP FALLBACK described in step 2a.3 of the skill -- shell out to scripts/fetch_today_meetings.py with credentials auto-loaded from ~/.claude/credentials/open-day.env. Do not silently fall back to yesterday's forward-look without trying the IMAP script first. Write the comprehensive daily note per my preferences (full task list, no Top 3 / vitality / pillars framing). Do not prompt me for energy or priorities. Just write the note and exit."
  "close-day"  = "Invoke the close-day skill from the nsls-personal-toolkit and run it non-interactively for today. Capture the work log, write the Insight Reflection, seed tomorrow's AI suggestions in tomorrow's daily note, and update the daily note. Leave the energy and reflection input fields blank for me to fill manually. Do not prompt me. Just write and exit."
  "open-week"  = "Invoke the open-week skill from the nsls-personal-toolkit and run it non-interactively for this week. Build this week's plan grounded in last week's close-out, this week's calendar, active projects, and carry-overs. Write the weekly note. Do not prompt me. Just write and exit."
  "close-week" = "Invoke the close-week skill from the nsls-personal-toolkit and run it non-interactively for the week ending today. Capture the week's results, write the weekly review, seed next week's AI suggestions in next week's weekly note, and update the weekly note. Do not prompt me. Just write and exit."
}

$Prompt = $Prompts[$Ritual]

$Header = "=== /$Ritual scheduled run started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz') ==="
Add-Content -Path $LogFile -Value $Header
Add-Content -Path $LogFile -Value ("Prompt: {0}" -f $Prompt)
Add-Content -Path $LogFile -Value "---"

# --dangerously-skip-permissions is required for unattended headless runs;
# the rituals only read Gmail/Airtable/Slack and write to the local Obsidian vault.
& $ClaudeBin -p $Prompt --dangerously-skip-permissions 2>&1 |
  ForEach-Object { Add-Content -Path $LogFile -Value $_ }

$Exit = $LASTEXITCODE
Add-Content -Path $LogFile -Value ("=== Exit code: {0} (finished {1}) ===" -f $Exit, (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))

# Slack ping so we know whether the headless run actually wrote anything.
# Failures here don't fail the ritual — log and move on.
$PingScript = Join-Path $PSScriptRoot "send-ritual-ping.ps1"
if (Test-Path $PingScript) {
  try {
    & $PingScript -Ritual $Ritual -ExitCode $Exit -LogFile $LogFile 2>&1 |
      ForEach-Object { Add-Content -Path $LogFile -Value ("[ping] " + $_) }
  } catch {
    Add-Content -Path $LogFile -Value ("[ping] ERROR: " + $_)
  }
} else {
  Add-Content -Path $LogFile -Value "[ping] send-ritual-ping.ps1 not found, skipping"
}

exit $Exit
