# Posts a Slack DM summarizing a scheduled ritual run.
# Called from run-claude-ritual.ps1 after the headless `claude` invocation finishes.
# Self-contained: only depends on the bot token + user id in ritual-pings.env.

param(
  [Parameter(Mandatory=$true)][ValidateSet("open-day","close-day","open-week","close-week")]
  [string]$Ritual,
  [Parameter(Mandatory=$true)][int]$ExitCode,
  [Parameter(Mandatory=$true)][string]$LogFile,
  # Override the date the ritual targeted (used for backfill). Default = today.
  [string]$RunDate,
  # Tag the message as a backfill so it's distinguishable from a live run.
  [switch]$Backfill,
  # Print the message text to stdout instead of posting to Slack. For testing.
  [switch]$DryRun
)

$ErrorActionPreference = "Continue"

# --- Load creds ---
$EnvFile = "C:\Users\apate\.claude\credentials\ritual-pings.env"
if (-not (Test-Path $EnvFile)) {
  Write-Error "ritual-pings.env not found at $EnvFile"
  exit 1
}
$envVars = @{}
Get-Content $EnvFile | ForEach-Object {
  if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$' -and -not $_.StartsWith('#')) {
    $envVars[$matches[1]] = $matches[2]
  }
}
$BotToken = $envVars['SLACK_BOT_TOKEN']
$UserId   = $envVars['SLACK_USER_ID']
if (-not $BotToken -or -not $UserId) {
  Write-Error "SLACK_BOT_TOKEN or SLACK_USER_ID missing from ritual-pings.env"
  exit 1
}

# --- Resolve expected Obsidian output file ---
$VaultPath = "C:\Users\apate\Obsidian\AP"
if ($RunDate) {
  $Today = [DateTime]::ParseExact($RunDate, "yyyy-MM-dd", $null)
} else {
  $Today = Get-Date
}
$DateStr = $Today.ToString("yyyy-MM-dd")

# ISO 8601 week (PowerShell 5.1 compatible -- no [System.Globalization.ISOWeek]).
# Approach: Thursday of $d's week determines both ISO year and ISO week.
# DST-safe: dates are normalized to UTC midnight before subtraction so spring-forward
# doesn't shave 23h off the diff and round 126 days down to 125.
function Get-IsoYearWeek([DateTime]$d) {
  $dow = [int]$d.DayOfWeek
  if ($dow -eq 0) { $dow = 7 }
  $thursday = $d.AddDays(4 - $dow)
  $thursdayUtc = [DateTime]::SpecifyKind($thursday.Date, [DateTimeKind]::Utc)
  $isoYear = $thursday.Year
  $jan4 = New-Object DateTime $isoYear, 1, 4, 0, 0, 0, ([DateTimeKind]::Utc)
  $jan4Dow = [int]$jan4.DayOfWeek
  if ($jan4Dow -eq 0) { $jan4Dow = 7 }
  $firstThursday = $jan4.AddDays(4 - $jan4Dow)
  $diffDays = [int][Math]::Round(($thursdayUtc - $firstThursday).TotalDays)
  $isoWeek = [int][Math]::Floor($diffDays / 7) + 1
  return [PSCustomObject]@{ Year = $isoYear; Week = $isoWeek }
}
$Iso = Get-IsoYearWeek $Today
$WeekStr = "{0}-W{1:D2}" -f $Iso.Year, $Iso.Week

switch ($Ritual) {
  "open-day"   { $OutFile = Join-Path $VaultPath "01-daily\$DateStr.md" }
  "close-day"  { $OutFile = Join-Path $VaultPath "01-daily\$DateStr.md" }
  "open-week"  { $OutFile = Join-Path $VaultPath "02-weekly\$WeekStr.md" }
  "close-week" { $OutFile = Join-Path $VaultPath "02-weekly\$WeekStr.md" }
}

# --- Markdown section extractor ---
# Returns the section starting at the first line matching $HeaderRegex (an H2 line),
# stopping at the next H2 (or end-of-file). Truncates to $MaxChars with an ellipsis.
# Returns $null if the section isn't found -- callers can fall back gracefully.
function Get-MarkdownSection {
  param(
    [Parameter(Mandatory=$true)][string]$FilePath,
    [Parameter(Mandatory=$true)][string]$HeaderRegex,
    [int]$MaxChars = 1500
  )
  if (-not (Test-Path $FilePath)) { return $null }
  $lines = Get-Content $FilePath -Encoding UTF8
  $inSection = $false
  $captured = New-Object System.Collections.ArrayList
  foreach ($line in $lines) {
    if ($line -match '^## ') {
      if ($inSection) { break }
      if ($line -match $HeaderRegex) {
        $inSection = $true
        [void]$captured.Add($line)
      }
    } elseif ($inSection) {
      [void]$captured.Add($line)
    }
  }
  if (-not $inSection) { return $null }
  $section = ($captured -join "`n").TrimEnd()
  if ($section.Length -gt $MaxChars) {
    $section = $section.Substring(0, $MaxChars).TrimEnd() + "`n_...truncated; see file for full content_"
  }
  return $section
}

# Returns up to $MaxLines lines from $FilePath that contain warning markers.
# Used to surface "no /close-day ran for X" type alerts the open-day skill writes
# at the top of the daily note.
function Get-WarningLines {
  param([string]$FilePath, [int]$MaxLines = 4)
  if (-not (Test-Path $FilePath)) { return @() }
  $matched = Get-Content $FilePath -Encoding UTF8 | Where-Object { $_ -match [char]0x26A0 -or $_ -match ':warning:' } | Select-Object -First $MaxLines
  return ,@($matched)
}

# --- Build the summary text ---
$RunTime = (Get-Date).ToString("HH:mm")
$Lines = @()
$BackfillTag = if ($Backfill) { " _(backfill ping for $DateStr)_" } else { "" }

if ($ExitCode -eq 0 -and (Test-Path $OutFile)) {
  $fileInfo = Get-Item $OutFile
  $sizeKb = [math]::Round($fileInfo.Length / 1024, 1)
  $modAgo = [int]((Get-Date) - $fileInfo.LastWriteTime).TotalMinutes
  $headings = (Select-String -Path $OutFile -Pattern '^## ' -AllMatches).Count

  # Sanity flag: if the file wasn't written/touched in the last 30 min, the run probably
  # didn't actually update it (e.g. claude exited 0 but produced nothing).
  # Skip the staleness check during backfill -- those are intentionally older.
  $stale = (-not $Backfill) -and ($modAgo -gt 30)

  $statusEmoji = if ($stale) { ":warning:" } else { ":white_check_mark:" }

  # --- Header ---
  $Lines += "$statusEmoji ``/$Ritual`` ran at $RunTime$BackfillTag"
  if ($stale) {
    $Lines += ":warning: File is older than this run -- claude may not have actually written it."
  }
  $Lines += ""

  # --- Per-ritual actionable content ---
  switch ($Ritual) {
    "open-day" {
      $warnings = Get-WarningLines -FilePath $OutFile
      if ($warnings.Count -gt 0) {
        $Lines += "*Warnings:*"
        $warnings | ForEach-Object { $Lines += "> $_" }
        $Lines += ""
      }
      $cal = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Calendar' -MaxChars 1000
      if ($cal) { $Lines += $cal; $Lines += "" }
      $tasks = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Tasks' -MaxChars 1500
      if ($tasks) { $Lines += $tasks; $Lines += "" }
      $week = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## W\d+ Context' -MaxChars 600
      if ($week) { $Lines += $week; $Lines += "" }
    }
    "close-day" {
      $insight = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Insight Reflection' -MaxChars 1500
      if ($insight) { $Lines += $insight; $Lines += "" }
      $airtable = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Airtable' -MaxChars 600
      if ($airtable) { $Lines += $airtable; $Lines += "" }
      $carry = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Carrying Over' -MaxChars 600
      if ($carry) { $Lines += $carry; $Lines += "" }
      # Tomorrow's seeded plan -- close-day's payoff for the next morning
      $tomorrow = $Today.AddDays(1).ToString("yyyy-MM-dd")
      $tomorrowFile = Join-Path $VaultPath "01-daily\$tomorrow.md"
      if (Test-Path $tomorrowFile) {
        $tomorrowSeed = Get-MarkdownSection -FilePath $tomorrowFile -HeaderRegex '^## Morning Check-in' -MaxChars 1200
        if ($tomorrowSeed) {
          $Lines += "*Tomorrow ($tomorrow) seeded:*"
          $Lines += $tomorrowSeed
          $Lines += ""
        } else {
          $Lines += "_Tomorrow ($tomorrow): note exists but no Morning Check-in section found._"
          $Lines += ""
        }
      } else {
        $Lines += ":warning: _Tomorrow ($tomorrow) note was NOT seeded._"
        $Lines += ""
      }
    }
    "open-week" {
      $mode = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Mode' -MaxChars 700
      if ($mode) { $Lines += $mode; $Lines += "" }
      $themes = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Themes' -MaxChars 800
      if ($themes) { $Lines += $themes; $Lines += "" }
      $top3 = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Recommended Top 3' -MaxChars 800
      if ($top3) { $Lines += $top3; $Lines += "" }
      $crit = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## Success Criteria' -MaxChars 600
      if ($crit) { $Lines += $crit; $Lines += "" }
    }
    "close-week" {
      # close-week's headline output is the digest it seeds into NEXT week's note.
      $nextWeek = $Today.AddDays(7)
      $nextIso = Get-IsoYearWeek $nextWeek
      $nextWeekStr = "{0}-W{1:D2}" -f $nextIso.Year, $nextIso.Week
      $nextWeekFile = Join-Path $VaultPath "02-weekly\$nextWeekStr.md"
      if (Test-Path $nextWeekFile) {
        $digest = Get-MarkdownSection -FilePath $nextWeekFile -HeaderRegex '^## W\d+ Close-out Digest' -MaxChars 2000
        if ($digest) {
          $Lines += "*Digest seeded into ${nextWeekStr}:*"
          $Lines += $digest
          $Lines += ""
        } else {
          $Lines += "_Next week ($nextWeekStr) note exists but no Close-out Digest section found._"
          $Lines += ""
        }
      } else {
        $Lines += ":warning: _Next week ($nextWeekStr) note was NOT seeded._"
        $Lines += ""
      }
      # Also surface this week's success-criteria result if close-week annotated it
      $crit = Get-MarkdownSection -FilePath $OutFile -HeaderRegex '^## (Success Criteria|W\d+ success criteria)' -MaxChars 600
      if ($crit) { $Lines += $crit; $Lines += "" }
    }
  }

  # --- Footer ---
  $Lines += "---"
  $Lines += "_File: ``$OutFile`` ($sizeKb KB, $headings sections, ${modAgo}m ago)_"
  $Lines += "_Log: ``$LogFile``_"
} else {
  # Failure path
  $Lines += ":x: ``/$Ritual`` failed at $RunTime (exit $ExitCode)$BackfillTag"
  $Lines += ""
  if (-not (Test-Path $OutFile)) {
    $Lines += "*Expected output:* ``$OutFile`` (NOT FOUND)"
  } else {
    $Lines += "*Expected output:* ``$OutFile`` (exists but exit code non-zero)"
  }
  $Lines += "*Log:* ``$LogFile``"
  if (Test-Path $LogFile) {
    $tail = Get-Content $LogFile -Tail 15 -Encoding UTF8 | Out-String
    $Lines += ""
    $Lines += "*Last 15 log lines:*"
    $Lines += '```'
    $Lines += $tail.TrimEnd()
    $Lines += '```'
  }
}

$MessageText = ($Lines -join "`n")

# Slack chat.postMessage hard limit is 4000 chars. Trim with a marker so we
# don't lose the footer and a too-long content block doesn't reject the post.
$SlackMax = 3800
if ($MessageText.Length -gt $SlackMax) {
  $MessageText = $MessageText.Substring(0, $SlackMax) + "`n_...message truncated to fit Slack 4k limit; see file_"
}

if ($DryRun) {
  Write-Output "=== DRY RUN: would send to user $UserId ==="
  Write-Output $MessageText
  Write-Output "=== end ==="
  Write-Output ("(message length: {0} chars)" -f $MessageText.Length)
  exit 0
}

# --- Send via Slack Web API: open DM, then post message ---
$Headers = @{
  "Authorization" = "Bearer $BotToken"
  "Content-Type"  = "application/json; charset=utf-8"
}

try {
  $openBody = @{ users = $UserId } | ConvertTo-Json -Compress
  $openResp = Invoke-RestMethod -Uri "https://slack.com/api/conversations.open" -Method Post -Headers $Headers -Body $openBody
  if (-not $openResp.ok) {
    Write-Error "Slack conversations.open failed: $($openResp.error)"
    exit 2
  }
  $channelId = $openResp.channel.id

  $postBody = @{
    channel = $channelId
    text    = $MessageText
    unfurl_links = $false
    unfurl_media = $false
  } | ConvertTo-Json -Compress -Depth 5

  # PS 5.1 Invoke-RestMethod sends bodies as Windows-1252 by default; force UTF-8
  # so multi-byte chars in the message don't break Slack's JSON parser.
  $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($postBody)
  $postResp = Invoke-RestMethod -Uri "https://slack.com/api/chat.postMessage" -Method Post -Headers $Headers -Body $bodyBytes
  if (-not $postResp.ok) {
    Write-Error "Slack chat.postMessage failed: $($postResp.error)"
    exit 3
  }
  Write-Output "Slack ping sent for /$Ritual (exit $ExitCode) -> ts=$($postResp.ts)"
  exit 0
} catch {
  Write-Error "Slack ping threw: $_"
  exit 4
}
