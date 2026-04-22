# Pre-meeting briefing agent

Automatically generates a 60-second scannable briefing before every 1:1, using only data you already have consented access to (Obsidian, Fathom, Gmail, Slack, Rippling).

**No web scraping. No surveillance of coworkers or their families.** See the ethics note at the bottom.

## What it does

For each meeting, it composes a markdown briefing with:

- **Personal** — family facts + recent life events already in their Obsidian profile
- **Where we left off** — last Fathom transcript: decisions, open action items, anything personal they mentioned
- **Live threads** — recent Gmail + Slack activity
- **Worth asking about** — one personal + one work follow-up
- **Suggested opener** — an actual sentence you could say

Output lands in `C:\Users\apate\Obsidian\AP\00-inbox\pre-meeting\` as `YYYY-MM-DD-HHMM-Person-Name.md`.

## Files

| File | Role |
|---|---|
| `briefing_prompt.md` | The prompt template Claude uses to compose each briefing |
| `run_briefings.py` | Orchestrator — reads calendar, loops meetings, invokes Claude CLI per person |
| `schedule_task.ps1` | Registers the Windows Task Scheduler entry (run ONCE) |
| `README.md` | This file |

## Setup (one-time)

```powershell
# In PowerShell
cd C:\Users\apate\.claude\.agents\pre-meeting-briefing
.\schedule_task.ps1
```

That registers a daily run at 6:00 AM that generates briefings for today + tomorrow.

## Usage

**Automatic (once scheduled):**
Runs every morning at 6:00 AM. Open `00-inbox/pre-meeting/` at the start of your day.

**On-demand:**

```bash
# Everything for today + tomorrow
python run_briefings.py

# Just today
python run_briefings.py --today

# Just tomorrow
python run_briefings.py --tomorrow

# A specific person (ad hoc — use any future time)
python run_briefings.py --email kprentiss@nsls.org --title "Kevin/Anish" --when "2026-04-28 14:00"
```

**From Claude Code:** type `/briefing kevin` or `/briefing today`.

## How it works

1. **Orchestrator** (`run_briefings.py`) queries Fathom for scheduled meetings on the target date. Filters to small meetings (≤4 invitees) with known SLT members, skips group standups.

2. **For each meeting**, invokes Claude CLI:
   ```
   claude -p "<briefing prompt + task params>" --permission-mode bypassPermissions
   ```
   The sub-session has MCP access to Fathom, Gmail, Slack. It reads the Obsidian profile, pulls recent data, and writes the briefing markdown.

3. **De-dupes** — one briefing per person per day. Rerun is a no-op if the file already exists.

## Ethics / guardrails

- **Data sources are all consent-based.** Fathom records meetings Anish is in; Gmail/Slack are his own accounts; Obsidian is his own notes; Rippling is his HR data for staff he manages.
- **No scraping.** No social media, no property records, no school websites, no whitepages. Personal facts about kids/spouses come only from what the person themselves mentioned in Fathom meetings.
- **Briefings are user-local.** Lands in Anish's Obsidian vault. Never synced to shared services, never committed to git.
- **No family surveillance.** If a family fact (e.g., a child's name) hasn't been said in a meeting, the briefing says "nothing surfaced" — it doesn't go looking.
