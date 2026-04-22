---
name: pre-meeting-briefing
description: >-
  Generate a 60-second pre-meeting briefing before any 1:1, assembling context
  from the person's Obsidian profile, last 3 Fathom transcripts, recent Gmail
  threads (14d), daily-note mentions (30d), and relationship-health state.
  Output lands in `00-inbox/pre-meeting/YYYY-MM-DD-HHMM-Person.md`. Runs
  automatically daily at 6 AM via Windows Task Scheduler; also callable via
  `/briefing <name>` or on-demand Python. Use when the user says "pre-meeting
  briefing", "brief me on X", "what's up with Kevin before our 1:1", "pull
  context on Y", "prep for my next meeting", or is about to walk into a 1:1
  and wants relationship capital, not surveillance. Dependencies: Fathom MCP
  configured, Gmail app password in `~/.claude/credentials/pre-meeting-briefing.env`,
  Obsidian vault at `C:/Users/apate/Obsidian/AP/`.
---

# Pre-meeting briefing

A 60-second scannable briefing before every 1:1, sourced only from data the user already has consent to use (their own Fathom recordings, their own Gmail, their own Obsidian notes, their own Rippling). **No web scraping. No social-media mining. No third-party data on coworkers' families.**

## Philosophy

**The value of personal signals is in the *asking*, not the *knowing*.** Walking into a 1:1 with a scraped fact about someone's child reads like surveillance. Walking in with context you've earned — from a meeting they were in, a note they sent, a moment they shared — reads like care.

This skill surfaces only what the person themselves has already told Anish in a meeting or email thread. If a fact (e.g., a child's name) isn't in Fathom or Obsidian, the briefing says "nothing surfaced" — it does not go looking elsewhere.

## When to run

- **Automatic:** Daily 6:00 AM via Windows Task Scheduler (`NSLS-Pre-Meeting-Briefings`). Generates briefings for today's + tomorrow's calendar.
- **On-demand slash command:** `/briefing kevin` or `/briefing today` or `/briefing tomorrow`.
- **Ad-hoc Python:** See [Usage](#usage) below.

## Data sources (in priority order)

1. **Obsidian profile** — `30-people/{Person}.md` — Personal, Character Traits, Relationship Health, last-met date.
2. **Fathom** (via the `fathom` MCP server) — last 3 transcripts with the person, keyed by invitee email. Latest transcript: full read. Prior 2: summaries only.
3. **Gmail** — pre-fetched by `scripts/fetch_gmail.py` via IMAP + app password. Last 14 days, FROM/TO/CC filter on the person's email.
4. **Slack** — not yet wired (Phase 2b). Current briefings skip Slack explicitly.
5. **Obsidian daily notes** — `01-daily/` grepped for mentions of the person's first or last name in last 30 days.

## Output format

A markdown file at `C:/Users/apate/Obsidian/AP/00-inbox/pre-meeting/YYYY-MM-DD-HHMM-Person-Name.md` with these sections:

- **In a sentence** — relationship health summary + biggest open item
- **Personal — things to remember** — profile facts + fresh personal mentions from recent Fathoms
- **Where we left off** — last Fathom's decisions + open action items both directions
- **Live threads** — email subjects (14d) + daily-note items (30d)
- **Worth asking about** — one personal question + one work follow-up
- **Suggested opener** — one literal sentence

Target length: under 400 words. Designed for a 60-second read right before the meeting.

## Setup (one-time)

### 1. Fathom MCP

Follow the Fathom seed in `/connect` skill. Requires a Fathom API key stored in `~/.claude/settings.json` under `mcpServers.fathom.env.FATHOM_API_KEY`.

### 2. Gmail app password

Generate at https://myaccount.google.com/apppasswords (requires 2FA on the Google account). Label it `Claude Code briefing agent`. Copy the 16-char password.

Write to `~/.claude/credentials/pre-meeting-briefing.env`:
```
GMAIL_USER=apatel@nsls.org
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

Chmod / ACL this file to owner-only. **Never commit**. The `.env` file must not land in the plugin repo.

### 3. Schedule the daily run

```powershell
# Once, from PowerShell
& "$HOME\.claude\local-plugins\nsls-personal-toolkit\skills\pre-meeting-briefing\scripts\schedule_task.ps1"
```

Registers a Windows Task Scheduler entry `NSLS-Pre-Meeting-Briefings` that runs daily at 6:00 AM, generating briefings for today + tomorrow.

## Usage

```bash
# Generate briefings for today AND tomorrow (default — this is what the scheduler runs)
python .../scripts/run_briefings.py

# Today only
python .../scripts/run_briefings.py --today

# Tomorrow only
python .../scripts/run_briefings.py --tomorrow

# Specific person, specific time (ad hoc)
python .../scripts/run_briefings.py --email kprentiss@nsls.org --title "Kevin/Anish" --when "2026-04-28 14:00"
```

From Claude Code: type `/briefing kevin` or `/briefing today`.

## How it works (architecture)

The Python orchestrator (`run_briefings.py`):
1. Loads credentials from `~/.claude/credentials/pre-meeting-briefing.env`.
2. Queries Fathom for meetings on the target date (calendar proxy — any real meeting has a Fathom record).
3. Filters to small meetings (≤4 invitees) with SLT members, skips SLT Huddle/All-Staff/Manager Preview.
4. For each meeting, pre-fetches Gmail threads with the target person via `fetch_gmail.py`.
5. Invokes `claude -p` in non-interactive mode with a prompt containing the task parameters + pre-fetched Gmail context + the briefing template (`briefing_prompt.md`).
6. The sub-session reads the profile, pulls Fathom transcripts via MCP, greps daily notes, composes the briefing markdown, writes to the output path.
7. Orchestrator exits; briefing is on disk.

De-duplication: one briefing per person per day. Re-running is a no-op if the file already exists.

## Guardrails

- **Consent-based sources only.** Fathom records meetings Anish is in; Gmail is his own account; Obsidian is his own notes; Rippling is HR data for staff he manages.
- **Zero scraping.** No social media, property records, school rosters, whitepages, obituaries. The briefing will NOT go looking for facts not already present in Anish's data.
- **User-local.** Briefings land in Anish's Obsidian vault, never synced to shared services, never committed to git.
- **Honesty over completeness.** If a section has no signal, writes "nothing surfaced" — does not invent.

## Files

| File | Role |
|---|---|
| `SKILL.md` | This file |
| `briefing_prompt.md` | Prompt template passed to `claude -p` per meeting |
| `README.md` | Extended documentation |
| `scripts/run_briefings.py` | Orchestrator — reads calendar, loops meetings, invokes Claude CLI |
| `scripts/fetch_gmail.py` | IMAP-based Gmail pre-fetcher |
| `scripts/schedule_task.ps1` | Windows Task Scheduler registration |

## Known gaps

- **Slack is not yet integrated.** Briefings skip Slack context entirely. Phase 2b adds this either via a Python Slack SDK + user token pre-fetch (mirroring the Gmail pattern), or by wiring Slack into the sub-session's MCP config.
- **Calendar source is Fathom, not Google Calendar directly.** Works for meetings that get recorded (99%+ of NSLS 1:1s), but ad-hoc unrecorded meetings won't auto-trigger a briefing. Workaround: call `/briefing <name>` manually.
- **No LinkedIn / public-professional context.** Could add in a future pass, but requires LinkedIn API access and scoping carefully to public-professional-only.
