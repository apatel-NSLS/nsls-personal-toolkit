# DESIGN.md — pre-meeting-briefing

*Design intent for the pre-1:1 briefing agent. Written 2026-04-22.*

## What this is (for the user)

A briefing note that lands in `Obsidian/AP/00-inbox/pre-meeting/` 5 minutes before every SLT 1:1, so you walk into the meeting already knowing:
- What you talked about last time (Fathom)
- What's live between you in email
- One personal thing worth asking about (from what they've already told you)
- A sentence you could literally open with

Runs automatically every morning at 6:00 AM via Windows Task Scheduler. No daily button to push.

## Customers

**Primary (1 user):** Anish Patel, NSLS CFO. Has 10 regular 1:1s/week across the SLT and adjacent roles.

**Indirect beneficiaries (~10 people):** Kevin, Gary, Adam, Ashleigh, Cory, Michael, Heather, Jenna, Chelsea, Jordan. They benefit from being met with care and memory, without knowing an AI was involved.

## UX principles

1. **60-second read.** Under 400 words, scannable on phone before a meeting starts. No walls of text.
2. **Consent-based sources only.** Fathom meetings Anish was in. His own Gmail. His own Obsidian notes. His own Rippling HR data. Nothing he doesn't already have a right to.
3. **"Nothing surfaced" is a valid answer.** If the briefing has no signal for a section, it says so. No invention, no confabulation.
4. **Asking > knowing.** Briefings surface personal prompts (e.g., "How's George feeling?") — not conclusions. The value is in asking the question, not in knowing the answer before they speak.
5. **Silent on fail.** If Fathom is down or Gmail times out, the briefing gracefully degrades and logs to `.run.log`. The scheduled task never crashes the morning.
6. **User-local.** Output lands in Anish's Obsidian vault. Never synced to shared services, never committed to git.

## What this should NOT become

- **A surveillance tool.** No scraping kids' school rosters, social media, obituaries, property records, or anything the target person didn't put into a meeting/email with Anish.
- **A dossier.** Briefings are *current*-context (last 14d email, last 3 Fathoms). They do not aggregate lifetime profiles for distribution.
- **An auto-send.** Anish reads the briefing. Nothing is sent to anyone else. Never "Claude wrote this" rapport.
- **A task manager.** Action items surface from Fathoms + email, but the skill doesn't enforce follow-up. That's `/open-day`'s lane.
- **A group-meeting briefer.** Filters out meetings with >4 invitees. The relational value is in 1:1s and small meetings; group standups get other tooling.
- **A substitute for actually asking.** Kevin's explicit critique in a 2026-04-10 Fathom ("you've had seven meetings with her and you don't know anything about her family") was the forcing function. The skill makes asking *easier*, not *unnecessary*.

## Interaction surface

- **Channel:** Markdown file in `Obsidian/AP/00-inbox/pre-meeting/`, opened in Obsidian right before the meeting.
- **Automatic trigger:** Windows Task Scheduler daily 6:00 AM for today + tomorrow's calendar.
- **Manual trigger:** `/briefing <name>` slash command in Claude Code; `python scripts/run_briefings.py --email X@nsls.org --title "..." --when "YYYY-MM-DD HH:MM"` on CLI.
- **Output:** Single markdown file per person per day. Idempotent — re-running is a no-op if the file exists.
- **Input to orchestrator:** Fathom list_meetings (calendar proxy), then for each matched meeting: Fathom transcript + Gmail (14d IMAP) + Obsidian profile + daily notes grep.

## Why this shape (alternatives considered + rejected)

- **"Just ask people more."** Works for 2–3 people. Breaks at 10+ per week across overlapping threads. Still the right answer for anything that matters enough to want remembered — the briefing should never replace the ask.
- **Full Google Cloud OAuth for Gmail.** Correct on paper, too much setup friction. App password + IMAP was one URL + 30 seconds. Tradeoff: no labels/threads richness, which we don't need for 14-day briefings.
- **Scrape social media / public profiles.** Ethically rejected. The signal's value is in the conversation, not the data point. Any AI-harvested family fact that surfaces in a 1:1 reads as creepy.
- **Build a persistent dossier service.** Over-engineered. A plain markdown file per person per day, written to the existing Obsidian vault, deletes itself naturally when the inbox gets cleaned.

## Measuring success

**Green signals (indicating it's working):**
- Anish opens the briefings before 1:1s (Obsidian file access timestamps prove this)
- SLT members feel *more* known over Q2, not less
- Anish can name all kids' names by end of June without hallucinating
- Zero instances of surfacing a fact the person didn't themselves share with him

**Red flags (kill or redesign immediately):**
- Briefing hallucinates a fact (e.g., invents a kid's name) → tighten the prompt, force explicit citations
- Any SLT member expresses discomfort that Anish "just knew" something → review that briefing's sources; likely we breached a boundary
- Scheduled task fails silently for >2 days → fix `.run.log` plumbing, add Slack alert on failure
- Anish stops reading the briefings → too long, or not useful; simplify

## Guardrails encoded in the implementation

- `fetch_gmail.py` validates `person_email` against an EMAIL_RE regex before any IMAP query — prevents IMAP command injection via malicious invitee strings.
- `run_briefings.py` enforces Fathom rate limits with 1.1-sec pacing on deep-pass mining (not this skill's runtime path, but the shared person-intelligence pattern this skill depends on).
- Credentials live in `~/.claude/credentials/pre-meeting-briefing.env` — outside any plugin repo. `.gitignore` excludes `.env` at the skill-dir level too as belt-and-suspenders.
- Subprocess timeouts (600s per Claude sub-session, 60s per Gmail fetch) ensure one bad meeting can't block the rest of the morning.

## Change log

- **2026-04-22** — Initial design. Built + committed + scheduled same day. Registered in NSLS Automation Tracker at Prototype stage; Anish listed as Code Owner + Maintainer.
- Next: Phase 2 = Slack integration (pre-fetch DMs + mentions the same way Gmail is pre-fetched).
