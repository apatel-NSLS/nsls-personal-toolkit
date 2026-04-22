---
name: board-tasks-tracker
description: >-
  Refreshes a daily Obsidian dashboard at Obsidian/AP/03-meta/board-tasks.md
  showing NSLS-board-related action items from the SLT Meeting Intelligence
  Airtable base, grouped by owner, sorted by due date, with flags for anything
  due before the next 45-day board meeting. Filters out student e-board noise.
  Runs daily at 7 AM via Windows Task Scheduler. Use when user says "board
  tasks", "what's due for the board", "board prep", "tracker for the board",
  or is preparing for a 45-day board meeting.
---

# Board Tasks Tracker

A dashboard for NSLS board-related action items — what's open, who owns it, when it's due, and what's critical before the next 45-day board meeting.

## Why this exists

Board meetings happen every 45 days. The action items assigned at each one get tracked in the Airtable SLT Meeting Intelligence base, but Airtable's UI buries them amongst hundreds of other tasks. This dashboard surfaces just the board-relevant subset, grouped by owner, so:

- The SLT walks into each 45-day meeting knowing exactly what's outstanding from the last one
- Cory (board administrator) can see what's owed to him and by him
- Anish (finance) can see which CFO items are blocking board decisions

## Scope

- **Included:** tasks mentioning "board meeting", "45-day", "board ask", "board prep", "advisory board", etc. Plus any task due within 14 days of the next board meeting date.
- **Excluded:** student chapter e-board tasks (keyword: "e-board", "eboard") — these are a different topic entirely.

## When to run

- **Automatic:** daily 7:00 AM via Windows Task Scheduler (`NSLS-Board-Tasks`).
- **On-demand:** `python scripts/refresh_board_tasks.py` or the `/board-tasks` slash command (future).

## Data source

- **Airtable:** SLT Meeting Intelligence base → Meeting Actions table.
  - Base ID: `appHDEHQA4bvlWwQq` (also in env as `AIRTABLE_SLT_BASE_ID`)
  - Table ID: `tblasgjUjadHCqzrg`
  - Auth: `AIRTABLE_PAT` from `~/.claude/local-plugins/nsls-personal-toolkit/.env`

## Output

Writes to `Obsidian/AP/03-meta/board-tasks.md`. Overwrites each run. Structure:

```markdown
---
type: dashboard
generated: {timestamp}
next_board_meeting: {YYYY-MM-DD}
---

# Board Tasks — Dashboard

## Next 45-day board meeting: {date}

## By owner
### {Owner 1}
- [ ] {task} — due {date} {(⚠️ if <7 days)}

### {Owner 2}
- ...

## Overdue
...

## Unassigned / no due date
...
```

## Configuration

`NEXT_BOARD_MEETING` date defaults to `2026-04-27` (next one as of skill creation). Update this constant in the script when the board calendar changes, OR read from a config file when the schedule is formalized.

## Ethics

Read-only against Airtable. No writes back.

## Files

| File | Role |
|---|---|
| `SKILL.md` | this |
| `scripts/refresh_board_tasks.py` | the renderer |
| `scripts/schedule_task.ps1` | Windows scheduled task registration |

## Related skills

- `/automation-tracker-dashboard` — sibling dashboard. Uses the same render-to-Obsidian pattern.
- `/open-day` — references this board-tasks page when the morning check-in happens close to a board meeting.
