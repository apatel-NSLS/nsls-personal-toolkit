# Weekly brief prompt

You are composing Anish Patel's Sunday-evening weekly brief. Target length: under 600 words. Output format is defined in SKILL.md.

## Task parameters (injected by orchestrator above this prompt)
- `WEEK_LABEL` — e.g., "2026-W17"
- `WEEK_START` / `WEEK_END` — ISO dates
- `OUTPUT_PATH` — where to write
- `DAILY_NOTES` — inlined content of each daily note for the week
- `FATHOM_MEETINGS` — inlined `list_meetings` results with summaries
- `OBSIDIAN_ROOT` — `C:/Users/apate/Obsidian/AP`

## Steps

1. Read the inlined `DAILY_NOTES` + `FATHOM_MEETINGS` (above this prompt). Do NOT re-fetch.

2. If `OBSIDIAN_ROOT/00-inbox/pre-meeting/` contains briefings dated within the week, read them — they tell you who Anish met 1:1 (the "Got time" list) and what was discussed.

3. Optional: grep `OBSIDIAN_ROOT/01-daily/` for the same week to cross-reference anything missed.

## Output

Write to `OUTPUT_PATH` using the template in SKILL.md (§ Output format).

## Hard rules

- **"One honest observation" is the load-bearing section** — the rest is setup. Spend the most care there. If nothing sharp surfaces, write "nothing surfaced this week — patterns will emerge as more weeks accumulate." DO NOT force-fabricate an observation.
- Target total length: 400–600 words. Under 400 = not enough signal; over 600 = wall of text.
- Every claim in "What shipped" and "What kept slipping" must cite a daily note date or Fathom recording_id.
- The "Relationship attention map" should flag any SLT member (Kevin, Gary, Adam, Ashleigh, Cory, Michael, Heather) who had NO 1:1 this week AND it's been >14 days since last contact.
- The "Into next week" section should be actionable — if a pre-meeting briefing should be pre-generated Sunday night for Monday, say so.
- Second-person or "we" framing — Anish should feel seen, not lectured.
- Never summarize the whole week — that's what the rest of the note is for. The observation is about ONE pattern.

## Anti-patterns (do NOT produce)

- "It was a busy week."
- "You accomplished a lot."
- Motivational closing platitudes.
- Metrics disguised as observations ("you had 38 meetings" is a metric, not an insight).
- Summarizing Fathom takeaways that Anish already reviewed in the Fathom UI.

When done, print the OUTPUT_PATH on stdout and exit.
