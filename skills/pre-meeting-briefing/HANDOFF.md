# HANDOFF guide — pre-meeting-briefing

*For: anyone who needs to pick this up if Anish is unavailable. "Won the lottery" document.*

## One-sentence summary

A Python orchestrator + Claude CLI sub-sessions + a Windows Task Scheduler trigger that produce 60-second pre-1:1 briefings into Obsidian every morning, sourced only from Fathom, Gmail, and Anish's notes.

## Who to contact

- **Primary owner + maintainer:** Anish Patel (apatel@nsls.org)
- **Technical escalation:** Kevin Prentiss (owns the NSLS Claude Code builder toolkit this plugin lives in)
- **Fathom MCP issues:** Fathom docs at https://developers.fathom.ai — the MCP server is a thin Python wrapper at `~/.claude/.mcp-servers/fathom/server.py`

## Where everything lives

| Thing | Path |
|---|---|
| Skill root | `~/.claude/local-plugins/nsls-personal-toolkit/skills/pre-meeting-briefing/` |
| Orchestrator | `scripts/run_briefings.py` |
| Gmail fetcher | `scripts/fetch_gmail.py` |
| Prompt template | `briefing_prompt.md` |
| Scheduled task registrar | `scripts/schedule_task.ps1` |
| Credentials | `~/.claude/credentials/pre-meeting-briefing.env` (NOT in the repo) |
| Output briefings | `~/Obsidian/AP/00-inbox/pre-meeting/` |
| Run log | `~/Obsidian/AP/00-inbox/pre-meeting/.run.log` |

## How to tell if it's working

```powershell
# See the scheduled task
Get-ScheduledTask -TaskName 'NSLS-Pre-Meeting-Briefings' | Get-ScheduledTaskInfo
# Last run time, last run result, next run time
```

If "LastTaskResult" is 0, it succeeded. Non-zero = failed — check `.run.log` in the output directory.

```bash
tail -20 ~/Obsidian/AP/00-inbox/pre-meeting/.run.log
```

## How to run it manually

```powershell
# Trigger the scheduled task on demand
Start-ScheduledTask -TaskName 'NSLS-Pre-Meeting-Briefings'

# Or directly
python "~\.claude\local-plugins\nsls-personal-toolkit\skills\pre-meeting-briefing\scripts\run_briefings.py" --today --tomorrow
```

## Required dependencies

- **Windows** (uses Task Scheduler and PowerShell)
- **Python 3.11+** with `fastmcp` and `httpx` installed globally: `python -m pip install fastmcp httpx`
- **Claude CLI** at `~/.local/bin/claude.exe` (installed via Claude Code)
- **Fathom MCP** configured in `~/.claude/settings.json` (see `/connect` skill, Fathom seed)
- **Gmail app password** stored in `~/.claude/credentials/pre-meeting-briefing.env` as `GMAIL_USER=...\nGMAIL_APP_PASSWORD=...`

## Environment variables used

| Variable | Source | Purpose |
|---|---|---|
| `FATHOM_API_KEY` | `~/.claude/settings.json` `mcpServers.fathom.env` | Fathom MCP auth (loaded automatically when the MCP starts) |
| `GMAIL_USER` | `~/.claude/credentials/pre-meeting-briefing.env` | IMAP login identity |
| `GMAIL_APP_PASSWORD` | same | 16-char Google app password (needs 2FA on the account) |
| `OBSIDIAN_VAULT_PATH` | optional, defaults to `~/Obsidian/AP` | Where briefings get written |
| `BRIEFING_MAX_PARALLEL` | optional, defaults to `3` | How many meetings to brief concurrently |

## How to rotate credentials

**Gmail app password:**
1. Revoke at https://myaccount.google.com/apppasswords
2. Generate a new one (name it "Claude Code briefing agent")
3. Replace the value in `~/.claude/credentials/pre-meeting-briefing.env`

**Fathom API key:**
1. Rotate at https://fathom.video/users/settings/api
2. Update `~/.claude/settings.json` → `mcpServers.fathom.env.FATHOM_API_KEY`
3. Restart Claude Code so the MCP picks up the new value

## Common failures + fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| No briefings in the folder after 6 AM | Scheduled task didn't run | `Get-ScheduledTaskInfo`; check if laptop was asleep |
| Briefing says "Gmail: not fetched" | `GMAIL_APP_PASSWORD` env var missing or password revoked | Check `~/.claude/credentials/pre-meeting-briefing.env`; rotate password if needed |
| Briefing has no Fathom context | Fathom MCP not connected or API key bad | Test: run `list_meetings` in a Claude session; rotate key if needed |
| Orchestrator crashes with `UnicodeEncodeError` | Windows CP1252 stdout | Already fixed in `fetch_gmail.py` — if you hit it elsewhere, set `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")` |
| Briefings are slow (>5 min each) | Claude CLI sub-session loading MCPs | Normal; expect 1–3 min per briefing |

## How to kill/pause the automation

```powershell
# Pause the scheduled task
Disable-ScheduledTask -TaskName 'NSLS-Pre-Meeting-Briefings'

# Unregister entirely
Unregister-ScheduledTask -TaskName 'NSLS-Pre-Meeting-Briefings' -Confirm:$false
```

## Ethics reminders (read before making changes)

- Only adds context from sources Anish already has consent to use.
- **Do NOT** add web scraping, social media harvesting, property-record lookup, or school-roster queries.
- If someone asks "can this also brief the OTHER person?" — no. This is Anish's personal prep tool.
- `DESIGN.md` has the full "what this should NOT become" section. Re-read before adding features.

## Monthly self-check

On the first of each month, spend 5 minutes:
1. Open 3 random briefings from the past week. Any hallucinations? Any facts citing non-existent sources? If yes, stop the task and fix the prompt.
2. Check `.run.log` for error patterns.
3. Verify Gmail + Fathom credentials still work.

If Anish has stopped opening the briefings (check Obsidian file access timestamps), the skill has failed its job and needs a redesign or sunset.
