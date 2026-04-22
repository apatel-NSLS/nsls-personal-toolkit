# HANDOFF guide — automation-tracker-dashboard

## One-sentence summary

Every day at 7 AM, a Python script pulls the Automation Tracker API and writes a markdown dashboard to Anish's Obsidian vault.

## Who to contact

- Owner: Anish Patel (apatel@nsls.org)
- API owner: Kevin Prentiss (owns the Railway-hosted proxy behind the Tracker)

## Where everything lives

| Thing | Path |
|---|---|
| Skill root | `~/.claude/local-plugins/nsls-personal-toolkit/skills/automation-tracker-dashboard/` |
| Script | `scripts/refresh_dashboard.py` |
| Scheduler | `scripts/schedule_task.ps1` |
| Output | `~/Obsidian/AP/03-meta/automations-dashboard.md` |

## Required dependencies

Python 3.11+ stdlib only. No pip installs. No MCPs.

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `OBSIDIAN_VAULT_PATH` | `~/Obsidian/AP` | Where the dashboard is written |
| `BUILDER_EMAIL` | `apatel@nsls.org` | Which builder's stats to emphasize |

## Health check

```powershell
Get-ScheduledTask -TaskName 'NSLS-Automation-Dashboard' | Get-ScheduledTaskInfo
```

Success = LastTaskResult 0.

```bash
ls -la ~/Obsidian/AP/03-meta/automations-dashboard.md
# Should be refreshed today
```

## Manual run

```bash
python ~/.claude/local-plugins/nsls-personal-toolkit/skills/automation-tracker-dashboard/scripts/refresh_dashboard.py
```

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| Exit 1 with "API unreachable" | Railway proxy down or network down | Wait; verify at https://web-production-6281e.up.railway.app/automations manually |
| TypeError on None comparison | Upstream API added a nullable field | Add `x.get("field") or default` guard |
| Dashboard stale (not refreshing) | Scheduled task disabled | `Enable-ScheduledTask -TaskName 'NSLS-Automation-Dashboard'` |

## How to pause/kill

```powershell
Disable-ScheduledTask -TaskName 'NSLS-Automation-Dashboard'
Unregister-ScheduledTask -TaskName 'NSLS-Automation-Dashboard' -Confirm:$false
```

## Monthly self-check

- Is the dashboard still useful? Open it, check if the sections surface what Anish actually uses.
- Has the Tracker API added new endpoints? Consider surfacing them.
- Is the SLT/Finance "Prototypes to watch" list actionable? If nobody ever follows up on it, kill that section.

## Won-the-lottery recovery

If Anish is out for a month and someone else needs to understand this:

1. It's read-only — can't break anything upstream.
2. If the scheduled task was removed for some reason, re-register via `scripts/schedule_task.ps1`.
3. If the Railway API URL changes, update it in `refresh_dashboard.py` (one constant, top of file).
4. If in doubt, you can kill the scheduled task without consequence — the dashboard just stops refreshing.
