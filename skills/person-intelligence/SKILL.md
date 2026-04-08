---
name: person-intelligence
description: >-
  Build or update a person profile, or run a biweekly relationship health check.
  Trigger: "person intel", "synthesize [name]", "build profile for [name]",
  "update [name]'s profile", "who is [name]", "person intelligence",
  "people profile", "refresh profiles", "relationship check", "health check",
  "biweekly check", "relationship health"
---

# Person Intelligence

Synthesizes rich person profiles into Obsidian (`30-people/[Name].md`) by pulling data from every available source: Fathom 1:1 transcripts, Airtable SLT meeting intelligence, Airtable People Ops, existing Obsidian notes, and conversation context.

Read `OBSIDIAN_VAULT_PATH` from `~/.claude/local-plugins/nsls-personal-toolkit/.env`.

Scripts live at: `~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/`

## Quick Start

"Synthesize Gary Tuerack" or "person intel on Adam Stone" -- the pipeline runs automatically.

## Pipeline

### Step 1: Identify the person

Ask for or confirm: full name, known email(s). Check the Known People Registry below for shortcuts.

### Step 2: Discover available data

Run these in parallel where possible. Each outputs JSON to stdout, status to stderr.

**Fathom 1:1s** (if email known):
```bash
python3.12 ~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/fetch_fathom_1on1s.py \
  --email {email} --list
```

**Airtable SLT** (if SLT member -- Gary, Adam, Ashleigh, Michael, Anish, Kevin):
```bash
python3.12 ~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/fetch_airtable_slt.py "{name}" > /tmp/person-intel-slt.json
```

**Airtable People Ops** (if NSLS employee):
```bash
python3.12 ~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/fetch_airtable_people_ops.py "{name}" > /tmp/person-intel-people-ops.json
```

**Existing Obsidian profiles** (vault at `$OBSIDIAN_VAULT_PATH`):
- `30-people/{Name}.md` (display name with spaces)
- `10-slt/members/{slug}.md` (lowercase hyphenated, e.g., `gary-tuerack.md`)
- `20-projects/board-intelligence/members/{Name}.md` (display name with spaces)

### Step 3: Fetch and summarize meetings

**If no email provided or Fathom returns 0 matches, skip this step.** The synthesizer works with Airtable data alone.

Fetch transcripts and summarize each:
```bash
python3.12 ~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/fetch_fathom_1on1s.py \
  --email {email} --fetch-all > /tmp/person-intel-meetings.jsonl

# Summarize each meeting (one Claude API call per meeting)
while IFS= read -r line; do
  echo "$line" | python3.12 ~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/summarize_meeting.py
done < /tmp/person-intel-meetings.jsonl > /tmp/person-intel-summaries.jsonl
```

**For weekly updates:** Add `--after {last-synthesized date}` to only fetch new meetings.

**Performance:** First runs with 20+ meetings take 20+ API calls. This is expected. Subsequent weekly runs are fast (1-3 new meetings).

### Step 4: Infer project connections

Assemble goals, actions, and topics from all sources into a JSON object and pipe to the inference engine:
```bash
python3.12 ~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/infer_projects.py < /tmp/person-intel-data.json
```

Input format: `{"goals": [...], "actions": [...], "topics": [...], "person_name": "..."}`
- Goals: from Airtable L1/L2/LOP goals
- Actions: from Airtable Meeting Actions
- Topics: from meeting summaries "Topics Discussed" sections

### Step 5: Synthesize profile

Assemble ALL collected data into a single JSON payload and synthesize:
```bash
python3.12 ~/.claude/local-plugins/nsls-personal-toolkit/skills/person-intelligence/scripts/synthesize_profile.py < /tmp/person-intel-combined.json > /tmp/person-intel-profile.md
```

Input format:
```json
{
  "person_name": "...",
  "meeting_summaries": [...],
  "airtable_slt": {...},
  "airtable_people_ops": {...},
  "existing_profile": "...",
  "existing_board_profile": "...",
  "existing_slt_profile": "...",
  "projects": {...}
}
```

All fields except `person_name` are nullable -- the synthesizer handles any combination.

### Step 6: Write to Obsidian

Write the synthesized profile to `$OBSIDIAN_VAULT_PATH/30-people/{Name}.md`.

If the person is an SLT member, also update `$OBSIDIAN_VAULT_PATH/10-slt/members/{slug}.md` with coaching feedback patterns (speaking %, contribution quality trends, start/stop recommendations over time).

If the person is a board member, do NOT overwrite `$OBSIDIAN_VAULT_PATH/20-projects/board-intelligence/members/{Name}.md` -- that has hand-curated board context. The `30-people/` profile links to it instead.

### Step 7: Surface project suggestions

If `infer_projects.py` returned "suggested" projects (1-2 matches, below the 3-match confirmation threshold), present them:

"I found possible project connections for {name}:
- **{project}**: mentioned {N} times ({evidence}). Add to profile?"

If confirmed, add to the profile AND update the project's `collaborators:` frontmatter.

### Step 8: Update project collaborators

For confirmed projects, update `$OBSIDIAN_VAULT_PATH/20-projects/{project}/{project}.md` frontmatter:
```yaml
collaborators: ["[[Gary Tuerack]]", "[[Cory Capoccia]]"]
```

This enables Obsidian dataview queries in `30-people/` hub files.

## Relationship Health Check

Trigger: "relationship check", "health check", "biweekly check"

### Scale (4 states, calibrated toward green)

| Score | Symbol | Label | Meaning |
|-------|--------|-------|---------|
| 1 | 🔴 | Needs Attention | Something's actively wrong |
| 2 | 🟡 | Watch | Drifting, needs course correction |
| 3 | 🟢 | Good | Healthy, productive, steady state (this is normal) |
| 4 | 💚 | Great | Peak collaboration, high trust, energizing |

### Six Dimensions

1. **Alignment** — Are we pulling in the same direction strategically?
2. **Trust** — Do I trust their judgment? Do they trust mine?
3. **Collaboration** — When we work together, is it productive or draining?
4. **Tension** — Is there unresolved friction? (4=none, 3=negligible, 2=some, 1=significant)
5. **Engagement** — Are they invested and showing up, or checked out?
6. **Influence Balance** — Am I leading this relationship or being led?

Rollup = average of 6 dimensions, mapped to emoji: ≥3.5 = 💚, ≥2.5 = 🟢, ≥1.5 = 🟡, <1.5 = 🔴

### How the Check Works

1. Read all `$OBSIDIAN_VAULT_PATH/30-people/*.md` files that have `health:` in frontmatter. **Skip files with `status: departed`** — their history is closed, no new assessments.
2. Present current state:

```
📊 Relationship Health — March 22, 2026

  💚 Gary Tuerack     (3.5) — last: Mar 22
  🟢 Cory Capoccia    (3.2) — last: Mar 22
  🟢 Adam Stone       (3.0) — last: Mar 22

Any changes? ("all good" to carry forward, or name who shifted)
```

3. If "all good" → carry forward all scores with today's date, no journal entry needed
4. If changes named → update those dimensions, recalculate rollup, ask to journal the thinking
5. Write updates:
   - Frontmatter: `health`, `health_score`, `health_last_assessed`, and update the `health-*` tag
   - H1: update emoji prefix (`# 💚 Name` / `# 🟢 Name` / `# 🟡 Name` / `# 🔴 Name`)
   - Append row to the health table
   - Append dated journal entry below the table

6. **Growth Reflection** (after relationship review):

After the relationship scores, prompt with 5 growth questions from Jack's framework:

```
🌱 Growth Check — March 22, 2026

1. Operating system — Did I zoom out this period, or was I in the wash?
2. Hard conversations — Did I have one? Did I avoid one?
3. Hero moments — Did I catch myself doing someone else's job?
4. Presence — How present was I? In meetings, at home?
5. Body — Exercise, sleep, energy?
```

Journal the reflection. Write it to `$OBSIDIAN_VAULT_PATH/20-projects/leadership-growth/leadership-growth.md`
under a new `### YYYY-MM-DD` entry in a `## Growth Journal` section.

Also check the most recent Jack Cohen session summary for any open commitments
and surface them: "Jack's last session (date): you committed to X. How did that go?"

### Journal Entry Format

Below the health table, reverse-chron journal entries. Free-form writing — this is where
you think through *why* the score is what it is. No length limit. The table is the dashboard,
the journal is the memory.

```markdown
### YYYY-MM-DD — 💚 Great

[Free-form thinking about this relationship right now.
Multiple paragraphs fine. This is private intelligence.]
```

### Obsidian Rendering

- **H1 emoji** shows current state when opening the file or in search
- **Graph coloring** via `health-great`, `health-good`, `health-watch`, `health-attention` tags
- **Health table** with emoji cells is a visual heatmap — scan patterns across time
- **Journal entries** below the table for context and reasoning

### CSS Snippet for Graph Coloring

Install at `$OBSIDIAN_VAULT_PATH/.obsidian/snippets/relationship-health.css`:

```css
/* Relationship health graph coloring */
.graph-view.color-fill-tag[data-tag="health-great"] .graph-view-node {
  fill: #22c55e !important;
}
.graph-view.color-fill-tag[data-tag="health-good"] .graph-view-node {
  fill: #86efac !important;
}
.graph-view.color-fill-tag[data-tag="health-watch"] .graph-view-node {
  fill: #facc15 !important;
}
.graph-view.color-fill-tag[data-tag="health-attention"] .graph-view-node {
  fill: #ef4444 !important;
}
```

## Weekly Automation

This skill supports incremental updates:
1. Only fetch Fathom meetings after the `last-synthesized` date from existing profile frontmatter
2. Re-pull Airtable data (goals/actions change frequently)
3. Merge new data with existing profile content
4. Surface new project suggestions if topics have shifted

## Known People Registry

| Name | Emails | Sources |
|------|--------|---------|
| Gary Tuerack | (check Fathom cache) | Fathom, SLT Airtable, People Ops, Board KB |
| Cory Capoccia | ccapoccia@nsls.org, cory.capoccia@gmail.com, cory@capocciaoffice.com | Fathom, Board KB |
| Adam Stone | (check Airtable) | SLT Airtable, People Ops |
| Ashleigh Smith | (check Airtable) | SLT Airtable, People Ops |
| Michael O'Brien | (check Airtable) | SLT Airtable, People Ops |
| Anish Patel | (check Airtable) | SLT Airtable, People Ops, Board KB |

Update this table as you profile new people.

## Script Reference

| Script | Input | Output | Requires |
|--------|-------|--------|----------|
| `fetch_fathom_1on1s.py` | `--email`, `--list`/`--fetch-all`/`--date` | JSON lines to stdout | FATHOM_API_KEY |
| `summarize_meeting.py` | JSON on stdin (transcript, title, date, person_name) | JSON line to stdout | ANTHROPIC_API_KEY |
| `fetch_airtable_slt.py` | person name as arg | JSON to stdout | AIRTABLE_API_KEY |
| `fetch_airtable_people_ops.py` | person name as arg | JSON to stdout | AIRTABLE_API_KEY |
| `infer_projects.py` | JSON on stdin (goals, actions, topics) | JSON to stdout | None |
| `synthesize_profile.py` | JSON on stdin (all data combined) | Markdown to stdout | ANTHROPIC_API_KEY |
