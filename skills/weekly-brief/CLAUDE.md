# CLAUDE.md — weekly-brief

*Instructions for Claude when working in this skill directory.*

## What this skill is

A Sunday-evening weekly synthesis agent. Runs at 7:00 PM every Sunday via Windows Task Scheduler. Composes a 400–600-word markdown brief at `Obsidian/AP/02-weekly/YYYY-WNN-brief.md` from that week's Obsidian daily notes, Fathom summaries, and pre-meeting briefings.

## Non-negotiable guardrails

- **The "One honest observation" section is load-bearing.** It's the reason the brief exists. If the data doesn't earn a sharp observation, write `"nothing surfaced this week — patterns will emerge as more weeks accumulate."` Do NOT fabricate.
- **No web scraping.** Same ethics posture as `pre-meeting-briefing`. Consent-based sources only.
- **Length cap: 600 words.** Anything longer fails the "2-minute Sunday read" design goal.
- **No motivational closings.** Anish explicitly does not want sycophancy.

## When editing the prompt

The prompt template is at `brief_prompt.md` (skill root, not in `scripts/`). The orchestrator pre-fetches daily notes + Fathom summaries + pre-meeting briefing filenames and inlines them. The sub-session must NOT re-fetch.

Examples of BAD observations to guard against (listed in the prompt):
- "It was a busy week." (generic)
- "You had 38 meetings." (metric, not observation)
- "Great job on the retreat." (sycophancy)

If you add a new observation archetype to the prompt, include a matching anti-pattern.

## When editing the orchestrator

- `run_weekly_brief.py` uses the Fathom MCP server's Python module directly (same pattern as `run_briefings.py`). It imports from `~/.claude/.mcp-servers/fathom/server.py`.
- The `read_daily_notes` function reads files raw — doesn't parse. If the daily-note template changes significantly, the inlined content will still work (Claude reads it as markdown).
- Run log at `OBSIDIAN_ROOT/02-weekly/.run.log`.

## Testing

```bash
# Dry-run mode — shows the assembled prompt without invoking Claude
python scripts/run_weekly_brief.py --dry-run

# Real run for a past week
python scripts/run_weekly_brief.py --week 2026-W16
```

## Relationship to other skills

- `/pre-meeting-briefing` — its output files are consumed by this skill's "Relationship attention map" section.
- `/open-week` / `/close-week` — complementary. Those are interactive rituals; this is a passive synthesis.
- `/open-day` — on Monday morning, reference the most recent weekly brief when seeding the day's priorities.

## Do NOT

- Send briefs to anyone other than Anish. This is personal.
- Aggregate across weeks into a dossier. If that's ever needed, build a separate skill.
- Add a "quarterly brief" version without re-running the design conversation — the honest-observation constraint may not hold over longer horizons.
