# HANDOFF guide — weekly-brief

*Won-the-lottery doc. If Anish is out and this skill is misbehaving, start here.*

## One-sentence summary

Every Sunday at 7 PM, a Python orchestrator collects the week's Obsidian daily notes + Fathom meeting summaries + pre-meeting briefings, and invokes Claude CLI to compose a 400–600-word weekly brief at `Obsidian/AP/02-weekly/YYYY-WNN-brief.md`.

## Who to contact

- Primary owner: Anish Patel (apatel@nsls.org)
- Technical escalation: Kevin Prentiss

## Where everything lives

| Thing | Path |
|---|---|
| Skill root | `~/.claude/local-plugins/nsls-personal-toolkit/skills/weekly-brief/` |
| Orchestrator | `scripts/run_weekly_brief.py` |
| Prompt template | `brief_prompt.md` |
| Scheduled task registrar | `scripts/schedule_task.ps1` |
| Output briefs | `~/Obsidian/AP/02-weekly/YYYY-WNN-brief.md` |
| Run log | `~/Obsidian/AP/02-weekly/.run.log` |

## Required dependencies

Same as `pre-meeting-briefing` (see its HANDOFF.md § Required dependencies):
- Python 3.11+ with no extra deps (uses stdlib only in the orchestrator)
- Fathom MCP configured (imports from `~/.claude/.mcp-servers/fathom/server.py`)
- Claude CLI at `~/.local/bin/claude.exe`

## Environment variables

| Var | Source | Purpose |
|---|---|---|
| `FATHOM_API_KEY` | `~/.claude/settings.json` | For the Fathom import |
| `OBSIDIAN_VAULT_PATH` | optional (defaults `~/Obsidian/AP`) | Where briefs get written |

## How to check health

```powershell
Get-ScheduledTask -TaskName 'NSLS-Weekly-Brief' | Get-ScheduledTaskInfo
```

LastTaskResult 0 = succeeded.

```bash
tail -20 ~/Obsidian/AP/02-weekly/.run.log
ls ~/Obsidian/AP/02-weekly/*-brief.md | tail -5
```

## How to run manually

```powershell
# This week
python ~\.claude\local-plugins\nsls-personal-toolkit\skills\weekly-brief\scripts\run_weekly_brief.py

# A specific past week
python ... --week 2026-W16

# Dry run — prints the prompt, doesn't invoke Claude
python ... --dry-run
```

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| No brief appears Sunday evening | Scheduled task didn't run | Check Task Scheduler, verify laptop was on at 7 PM |
| Brief says "no daily notes found" | Daily-note path or OBSIDIAN_VAULT_PATH mismatch | Check `01-daily/YYYY-MM-DD.md` exists for the week |
| Brief says "(Fathom fetch failed)" | MCP server import error | Check `~/.claude/.mcp-servers/fathom/server.py` + `FATHOM_API_KEY` |
| Brief has no observation | Honest-observation rule correctly fired | Not a bug — `"nothing surfaced"` is valid output |
| Brief is longer than 600 words | Prompt drifted | Re-tighten `brief_prompt.md` length rule |

## How to pause/kill

```powershell
Disable-ScheduledTask -TaskName 'NSLS-Weekly-Brief'            # pause
Unregister-ScheduledTask -TaskName 'NSLS-Weekly-Brief' -Confirm:$false  # remove
```

## Monthly self-check

On the 1st of each month:
1. Read the last 4 weekly briefs. Any hallucinations? Any fake citations? If yes, tighten the prompt.
2. Check `.run.log` for error patterns.
3. If Anish has stopped opening the briefs (Obsidian access timestamps), investigate — something's broken or the skill isn't earning its keep.
