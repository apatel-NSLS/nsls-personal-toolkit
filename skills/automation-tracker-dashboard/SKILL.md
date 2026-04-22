---
name: automation-tracker-dashboard
description: >-
  Refreshes a single Obsidian dashboard page at Obsidian/AP/03-meta/automations-dashboard.md
  showing all 28+ NSLS automations by stage, Anish's owned automations with
  checklist progress, recent stage advancements, and which SLT members' automations
  need attention. Runs daily at 7 AM via Windows Task Scheduler. Pulls from the
  Automation Tracker API at web-production-6281e.up.railway.app (read-only). Use
  when user says "automation dashboard", "show me the tracker", "what's the
  automation state", "tracker status", or on first check-in of the day.
---

# Automation Tracker Dashboard

A single-page daily snapshot of the NSLS Automation Tracker, written to Obsidian so Anish can see the whole automation portfolio at a glance without opening Airtable.

## Why this exists

The Automation Tracker is the source of truth for NSLS automation portfolio but its Airtable UI doesn't make trends obvious — you can't easily see "which of my automations are closest to Production", "who in SLT is shipping and who isn't", or "what was registered this week".

This dashboard materializes those views into a markdown page that lives in Anish's vault, refreshes daily, and is searchable + linkable like any other Obsidian note.

## What's in it

1. **Portfolio at a glance** — counts by stage (Prototype / Production / Org-Owned), counts by department, counts by type.
2. **Anish's automations** — each with checklist completion percentage + remaining items.
3. **Recent stage advancements** — which automations moved between stages in the last 14 days.
4. **SLT leaderboard** — automations owned by each SLT member; flag anyone with zero automations in >30 days as "dormant" (not in a competitive sense — as a relationship signal for Anish).
5. **Ready to advance** — automations with ≥8 checklist items checked that haven't advanced in 14 days (nudge opportunity).

## When to run

- **Automatic:** Daily 7:00 AM via Windows Task Scheduler (`NSLS-Automation-Dashboard`), right before `/open-day`.
- **On-demand:** `python scripts/refresh_dashboard.py` or the `/tracker` slash command.

## Data sources

- `GET https://web-production-6281e.up.railway.app/automations` — full list
- `GET https://web-production-6281e.up.railway.app/builder-stats/apatel@nsls.org` — Anish's portfolio + recent events

## Output

Writes to `Obsidian/AP/03-meta/automations-dashboard.md`. Overwrites each run. Backlinks survive (so linking to this page from daily notes still works).

## Files

| File | Role |
|---|---|
| `SKILL.md` | this |
| `scripts/refresh_dashboard.py` | pulls API, renders markdown |
| `scripts/schedule_task.ps1` | Windows scheduled task |

## Guardrails

- Read-only against the Tracker API. No writes.
- Deterministic output — two runs within the same minute produce identical files.
- No PII. Automation names and owner emails only.
