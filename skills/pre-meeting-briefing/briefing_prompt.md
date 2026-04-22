# Pre-meeting briefing task

You are generating a pre-meeting briefing for Anish Patel (NSLS CFO). Your job is to turn existing data into a 60-second scannable note that helps Anish walk into the meeting with relationship capital.

## Input (injected by the orchestrator)
- `PERSON_NAME` — e.g., "Kevin Prentiss"
- `PERSON_EMAIL` — e.g., "kprentiss@nsls.org"
- `MEETING_TITLE` — e.g., "Kevin/Anish"
- `MEETING_WHEN` — ISO timestamp
- `OUTPUT_PATH` — where to write the markdown

## Data sources to use (in this order)

1. **Obsidian profile:** Read `C:/Users/apate/Obsidian/AP/30-people/{PERSON_NAME}.md` — pull the Personal section, Character Traits, last meeting date, recent health score. Skim the Meeting Log for the last 3 interactions.

2. **Fathom — last 3 transcripts with this person:**
   - Run: `FATHOM_API_KEY="..." python C:/Users/apate/.claude/.mcp-servers/fathom/cache/find_recent.py --email {PERSON_EMAIL} --limit 3` (if it exists) OR call `mcp__fathom__list_meetings` with `invitee_email={PERSON_EMAIL}` to get recent recordings
   - For the latest 1 meeting: pull full transcript via `mcp__fathom__get_transcript` to see what was actually discussed
   - For the other 2: fetch summaries via `mcp__fathom__get_summary` (cheaper, still informative)
   - Extract: key decisions, open action items on either side, anything personal they mentioned

3. **Gmail — last 14 days of threads with this person:**
   - **The orchestrator has already fetched this** — look for the "Gmail context (pre-fetched, inline below)" block in the task parameters above the rules section. Use those subjects and snippets directly for the "Live threads > Email" section. DO NOT call the Gmail MCP yourself.
   - Extract: open subjects, any asks awaiting response, any flagged urgency
   - If the block says "not fetched" or "no recent threads", write "nothing surfaced" in the Email line.

4. **Slack — last 7 days of DMs/mentions:**
   - Use `mcp__9434446a-*__slack_search_public_and_private` with the person's handle or name + recent date filter
   - Also `mcp__9434446a-*__slack_read_channel` for the DM with them if accessible
   - Extract: any live threads, pending questions

5. **Obsidian daily notes — last 30 days mentioning this person:**
   - Grep `C:/Users/apate/Obsidian/AP/01-daily/` for their first name + last name
   - Extract: anything Anish logged about them recently

## Output format

Write to `{OUTPUT_PATH}` (a markdown file). Keep it under 400 words total. Structure:

```markdown
# {PERSON_NAME} — pre-meeting briefing
*Meeting: {MEETING_TITLE} · {MEETING_WHEN}*

## In a sentence
{1-sentence summary of where the relationship is right now — health score + key open item}

## Personal — things to remember
- {3–5 bullets from profile Personal section, especially family + recent life events}
- {Any personal item they mentioned in last 1–2 Fathoms, as a callable follow-up question}

## Where we left off (last Fathom · {date})
- {2–3 bullets on what was actually discussed — decisions, unresolved threads}
- **Open from them → you:** {if any}
- **Open from you → them:** {if any}

## Live threads
- **Email:** {1–2 subjects from last 14d, 1 line each}
- **Slack:** {1–2 threads from last 7d, 1 line each}

## Worth asking about
- {ONE personal question — e.g., "How's George feeling?" or "How was the Colorado trip?"}
- {ONE work follow-up — e.g., "Did the Ignite bundle ship?"}

## Suggested opener
> {One short line Anish could literally say to open the meeting}
```

## Important rules

- **Honesty over completeness.** If a section has no signal, write "nothing surfaced" — do NOT invent.
- **Cite the Fathom recording_id** for any direct quote.
- **Do not include PII beyond what's already in Anish's vault.** (This is his own note; treat it as private.)
- **Be fast.** Don't narrate your work; write the file and stop.
- **Do not edit the person's profile** from this task — briefings go to `00-inbox/pre-meeting/` only.

When done, print the output path on stdout and exit.
