# CLAUDE.md — automation-tracker-dashboard

*Instructions for Claude when editing this skill.*

## What this skill is

A daily read-only dashboard generator. Pulls the NSLS Automation Tracker API at `web-production-6281e.up.railway.app` and renders a single Obsidian page at `Obsidian/AP/03-meta/automations-dashboard.md`. Runs at 7:00 AM daily via Windows Task Scheduler.

## Key behavior

- **Read-only.** Never PATCHes, POSTs, or DELETEs upstream. If someone asks for write features, push back — the Tracker is Kevin's source of truth and writes go through `/register-automation`.
- **Deterministic.** Two runs within the same minute produce identical files (aside from the `generated:` timestamp in frontmatter). No randomness, no LLM calls.
- **Overwrites.** The dashboard file is re-rendered each run. Backlinks to the file survive; backlinks to content inside don't (but Obsidian handles this gracefully).
- **Uses stdlib only.** No httpx, no external deps. This keeps it trivially portable + reviewable.

## When editing the renderer

- The markdown structure is defined in `render()`. If you add a section, add it in a consistent position — don't reorder existing ones (Anish has muscle memory for where each block lives).
- None-safety: always use `x.get("field") or default`. The API returns `null` for unset fields (e.g., department is None for a few records). Naive `.get(key, default)` doesn't catch None → string sort breaks.
- Keep table columns narrow enough to render in Obsidian preview without horizontal scroll.

## When editing API calls

- Endpoints: `/automations`, `/builder-stats/{email}`. Add more carefully — some endpoints (`/find`, `/register-*`) have side effects.
- Budget: one script run = 2 HTTP requests. Stay there. Don't per-automation-fetch.
- Timeout: 20s. If the API is down, the script fails loudly (exit 1, stderr). That's correct — silent failure would mislead Anish.

## Do NOT

- Add writes (create/update/delete automations). That's `/register-automation`'s job.
- Fetch per-automation checklist detail in a loop — the API doesn't support it efficiently today, and a loop across 30 automations would be slow + rate-limit-prone.
- Render more than 30–40 automations in the "Full portfolio" list without pagination — it becomes a wall of text.
- Send the dashboard anywhere (Slack, email). It's a local reference page.

## Testing

```bash
python scripts/refresh_dashboard.py
# Open Obsidian/AP/03-meta/automations-dashboard.md
```

If the output looks off, check:
1. Is the API up? `curl https://web-production-6281e.up.railway.app/automations`
2. Did a new field appear in the API response? Look at `render()` and guard it.
