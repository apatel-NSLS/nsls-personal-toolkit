---
name: weekly-brief
description: >-
  Generate a weekly synthesis every Sunday evening — pulls the week's daily
  notes, Fathom summaries, Gmail threads, and completed/missed commitments into
  one scannable "week in review" markdown page. Surfaces patterns Anish might
  otherwise miss: what kept slipping, what actually shipped, which relationships
  got attention vs. drift, where time went vs. where he thought it went. Runs
  automatically Sunday 7 PM via Windows Task Scheduler. Use when user says
  "weekly brief", "week in review", "weekly synthesis", "what happened this
  week", "weekly retrospective", or on Sunday evening open-week routine.
  Output lands at Obsidian/AP/02-weekly/YYYY-WNN-brief.md.
---

# Weekly Brief

A synthesis of the week — what shipped, what slipped, where time went, which relationships got attention, and one honest observation worth sitting with before Monday.

## Philosophy

The week has a shape that the individual days don't show. Daily notes are too close-in; quarterly reviews are too far-out. A Sunday evening synthesis hits the sweet spot: Anish can still feel every day of the week, but he can also see patterns that only emerge across ~5 business days.

**Design intent (parallel to pre-meeting-briefing):** consent-based sources only, honest "nothing surfaced" over invention, under 600 words, one sharp observation over five generic ones.

## When to run

- **Automatic:** Sundays at 7:00 PM via Windows Task Scheduler (`NSLS-Weekly-Brief`).
- **On-demand:** `/weekly-brief` slash command or `python scripts/run_weekly_brief.py`.
- **Ad-hoc for a past week:** `python scripts/run_weekly_brief.py --week 2026-W16`.

## Data sources

1. **Obsidian daily notes** for the week — `01-daily/YYYY-MM-DD.md` from Mon–Sun. Read the Work Log + Brain Dump + End of Day sections.
2. **Pre-meeting briefings** generated that week — `00-inbox/pre-meeting/*.md`. Who did Anish meet with 1:1? How well-attended vs. rescheduled?
3. **Fathom meetings** for the week — `mcp__fathom__list_meetings(recorded_after=..., recorded_before=...)`. For each: title, attendees, default_summary. No full transcripts (too much volume); summaries only.
4. **Gmail** — threads Anish sent (as a proxy for "what he drove") and threads where he was the last responder ("what's on his plate going into next week").
5. **Airtable tasks closed / still open** for the week — from the Meeting Actions table with `assignee_email=apatel@nsls.org`.

## Output format

Write to `Obsidian/AP/02-weekly/YYYY-WNN-brief.md` (where WNN is the ISO week number). Structure:

```markdown
# Week NN — {start date} to {end date}
*Generated {timestamp}*

## In a sentence
{1-sentence week summary — what was this week about?}

## What actually shipped
- {3–5 bullets of real completions, cited to daily note or Fathom}

## What kept slipping
- {items that appeared in multiple daily-note carry-overs}
- {meetings rescheduled 2+ times}

## Where the time went
- Meetings: {count} ({hours}h)
- Focus work: {count of focus blocks} ({hours}h)
- Inbound/reactive: {heuristic estimate}
- Top 3 topic clusters: {from Fathom titles + daily notes}

## Relationship attention map
- **Got time:** {people Anish met with 1:1 this week}
- **Got drift:** {SLT members with no 1:1 this week — flag if >14 days since last}
- Follow-ups owed: {open action items from the week's 1:1s, unresolved}

## One honest observation
{ONE thing worth sitting with. Not a summary. Something the week revealed that Anish might not have named to himself. Cite the evidence.}

## Into next week
- {2–3 things to carry / lead with on Monday}
- {any new pre-meeting briefings to pre-generate for Monday}
```

**Length target:** under 600 words. Designed as a 2-minute Sunday-evening read.

## Honest observation — non-negotiable rule

The "One honest observation" section is the load-bearing part of this brief. It is NOT a summary. It is NOT motivational. It is the ONE pattern from this week that Anish might not have named to himself.

Examples of a good observation:
- *"You rescheduled the Kevin 1:1 three times this week, but called Gary twice. That's not bandwidth — that's avoidance."*
- *"You shipped the deck but you haven't followed up on the three delegations you made last Monday. Delegation without follow-up isn't delegation."*
- *"Two daily notes said 'I'll handle the investment sheet rebuild this week.' The third said 'Erin will draft it.' You didn't drop it; you reframed it. Good move."*

Examples of a BAD observation (do not produce):
- *"It was a busy week."* (useless)
- *"You had 38 meetings and shipped 2 deliverables."* (that's a metric, not an observation)
- *"Great job on the retreat."* (sycophancy — Anish hates this)

If no sharp observation is earned by the data, **write "nothing surfaced" — do NOT force one.**

## Files

| File | Role |
|---|---|
| `SKILL.md` | This file |
| `DESIGN.md` | Intent + what this should NOT become |
| `CLAUDE.md` | Instructions for future Claude edits |
| `HANDOFF.md` | Bus-factor doc |
| `brief_prompt.md` | Prompt template passed to `claude -p` |
| `scripts/run_weekly_brief.py` | Orchestrator |
| `scripts/schedule_task.ps1` | Windows Task Scheduler registration |

## Ethics guardrails (same as pre-meeting-briefing)

- Consent-based sources only — no scraping, no social media, no external lookups
- User-local output — never syncs to shared services
- "Nothing surfaced" is a valid answer; never invent
- Weekly briefs are deleted after 90 days (auto-purge by orchestrator on run) to prevent drift into a dossier

## Related skills

- `/open-day` — consumes the "Into next week" section on Monday
- `/pre-meeting-briefing` — weekly brief cross-references these and flags gaps
- `/open-week` / `/close-week` — existing skills this complements; use weekly-brief for the synthesis they don't do
