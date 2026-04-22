# CLAUDE.md — pre-meeting-briefing

*Instructions for Claude when working in this skill directory.*

## What this skill is

A pre-1:1 briefing agent that runs at 6:00 AM daily via Windows Task Scheduler and produces 60-second markdown briefings in `Obsidian/AP/00-inbox/pre-meeting/`. Source-of-truth files:

- `SKILL.md` — canonical description + usage
- `DESIGN.md` — UX principles, what this should NOT become, alternatives considered
- `README.md` — operational docs (setup, usage, architecture)
- `scripts/run_briefings.py` — orchestrator
- `scripts/fetch_gmail.py` — IMAP-based Gmail pre-fetcher
- `scripts/schedule_task.ps1` — Windows Task Scheduler registration

## Non-negotiable guardrails

If you modify this skill, **do not** add:
- Web scraping of any social media, property records, school rosters, or public profiles
- Automated lookup of family members outside what the subject has already shared with Anish in Fathom/Gmail
- Any output that gets sent to anyone other than Anish (no auto-DMs, no "brief the other person too")
- Any feature that aggregates briefings into a cross-person dossier

These rejections are documented in `DESIGN.md § What this should NOT become`. If in doubt, re-read DESIGN.md before adding a feature.

## Credentials live outside the plugin repo

Never commit `.env` files. The skill's `.gitignore` excludes `.env*`. Credentials live at `~/.claude/credentials/pre-meeting-briefing.env` — user-local, user-managed.

## When editing run_briefings.py

- The orchestrator invokes `claude -p` per meeting via subprocess. Handle `TimeoutExpired` and `FileNotFoundError`.
- Validate any email interpolated into IMAP queries against `EMAIL_RE` first — Gmail's X-GM-RAW search is not injection-safe otherwise.
- Env propagation: always pass `env={**os.environ, ...}` to subprocesses; never `env={}` (kills PATH).
- Keep the parallel executor at `max_workers=3` max — the Claude CLI has its own rate limits upstream.

## When editing fetch_gmail.py

- Reuse the `EMAIL_RE` regex validation at entry. Do NOT trust callers.
- Gmail folder `[Gmail]/All Mail` needs quoted form: `mail.select('"[Gmail]/All Mail"')`.
- `X-GM-THRID` and `RFC822` can be fetched in a single `mail.fetch()` call — don't split into two round-trips.

## When editing the briefing prompt

- The prompt is in `briefing_prompt.md` at the skill root (not in `scripts/`).
- The orchestrator injects task parameters + pre-fetched Gmail context above the prompt template. The sub-session knows not to re-fetch Gmail (instructed in the prompt).
- Keep output under 400 words. Target 60-second read. Every claim must cite a Fathom recording_id or other source.

## Running smoke tests

```bash
python scripts/run_briefings.py --email kprentiss@nsls.org --title "Test" --when "2026-05-01 14:00"
```

Wait ~2 minutes per briefing. Output lands in `Obsidian/AP/00-inbox/pre-meeting/`. Check `.run.log` in that directory for failures.

## Maintenance checklist

If this skill has been quiet for >90 days:
- Verify the scheduled task still runs: `Get-ScheduledTask -TaskName 'NSLS-Pre-Meeting-Briefings' | Get-ScheduledTaskInfo`
- Check the last 3 days of briefings are present in `Obsidian/AP/00-inbox/pre-meeting/`
- Rotate the Gmail app password if it's been >1 year
- Re-review `DESIGN.md` to make sure the guardrails still hold
