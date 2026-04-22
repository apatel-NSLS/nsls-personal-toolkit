# DESIGN.md — weekly-brief

*Design intent for the Sunday-evening weekly synthesis. Written 2026-04-22.*

## What this is (for the user)

Every Sunday at 7 PM, a ~500-word markdown page that tells Anish what his week actually was — not what he remembers it being. What shipped, what kept slipping, where the time actually went, which relationships got attention vs. drift, and one honest observation worth sitting with before Monday.

## Customers

**Primary (1 user):** Anish Patel, NSLS CFO.

**Indirect beneficiaries:** the SLT, by way of Anish walking into Monday more aware of patterns he'd otherwise miss (e.g., "I haven't had a 1:1 with Michael in 3 weeks" surfaces here before it surfaces as drift).

## UX principles

1. **2-minute read.** 400–600 words. Anything longer fails.
2. **One sharp observation over five generic ones.** The entire brief is setup for the observation. If no sharp observation is earned, write "nothing surfaced" — do not force one.
3. **Citation-backed claims.** "What shipped" and "What kept slipping" must cite a daily note date or Fathom recording_id.
4. **Relationship drift is a first-class signal.** If 14+ days have elapsed since Anish last had a 1:1 with an SLT member, the brief flags it.
5. **Into-next-week is actionable.** Not "plan your week" — specific carry-overs + specific pre-meeting briefings to trigger for Monday.
6. **No motivational closings.** Anish has said directly he dislikes sycophancy.

## What this should NOT become

- **A summary of everything.** Summary = the rest of the note. The brief's job is the one observation.
- **A performance report.** Not "you accomplished X, Y, Z" — that's a metric list disguised as reflection.
- **Motivational journaling.** No "celebrate your wins!" framing. The brief should make Anish think, not feel better.
- **A shared document.** This is personal. Do not add a feature to share/send it.
- **A quarterly or monthly equivalent.** The 2-minute-read constraint + the observation constraint may not hold over longer horizons. Design those separately.
- **A checklist grader.** The brief does not judge "did you hit your Top 3." The feedback memory on `/open-day` explicitly rejected Top 3 framing.

## Interaction surface

- **Channel:** Markdown file in `Obsidian/AP/02-weekly/`.
- **Automatic trigger:** Windows Task Scheduler Sunday 7:00 PM.
- **Manual trigger:** `python run_weekly_brief.py` or (future) `/weekly-brief` slash command.
- **Inputs:** Obsidian daily notes for the ISO week + Fathom `list_meetings` (with summaries) + pre-meeting briefing filenames.
- **Output:** single markdown file per week. Idempotent — rerun is a no-op if file exists.

## Why this shape (alternatives considered)

- **Manual Sunday retrospective.** The obvious alternative. Fails because (a) Anish doesn't do it consistently, (b) even when he does, he remembers narrative more than pattern. The synthesis is load-bearing — an LLM can see pattern across 5 daily notes where a human sees narrative.
- **Metric dashboard instead of prose.** Would show meeting counts, hours, etc. But the question isn't "how much" — it's "what mattered." Prose with one observation beats a dashboard.
- **Cross-person briefs** (e.g., "here's your whole SLT this week"). Tried conceptually. The per-meeting briefing in `/pre-meeting-briefing` is the right grain for relationships; the weekly brief is about the week's shape, not each person's.

## Measuring success

**Green signals:**
- Anish opens each weekly brief (Obsidian access timestamps).
- The observation section occasionally surprises him — something he hadn't named.
- Monday mornings feel less noisy because Sunday did the synthesis work.

**Red flags (investigate or kill):**
- Observation section is generic or sycophantic — tighten prompt.
- Anish can predict the observation without reading — the brief isn't earning its keep.
- Week after week saying "nothing surfaced" — either the data isn't rich enough yet, or the brief's bar is too high.

## Guardrails encoded in the implementation

- Subprocess timeout (900s) + structured `.run.log`.
- Idempotent: exists-check before write.
- Consent-based sources only (no scraping, same as `pre-meeting-briefing`).
- No dependencies beyond stdlib + Fathom MCP import — portable, inspectable.

## Change log

- **2026-04-22** — Initial design. Built + committed + scheduled same day. Registered at Prototype in the NSLS Automation Tracker.
