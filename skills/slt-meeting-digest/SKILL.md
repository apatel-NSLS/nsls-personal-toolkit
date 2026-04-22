---
name: slt-meeting-digest
description: >-
  Every 15 minutes, polls Fathom for recently-completed SLT meetings and posts
  a 3-bullet digest + action items to a Slack channel (default `#slt-ops`) so
  people who missed the meeting get caught up instantly. Runs via Windows Task
  Scheduler every 15 min. If a Slack bot token is not yet configured, falls
  back gracefully to writing the digest to Obsidian/AP/00-inbox/slt-digest/
  for Anish to post manually. Use when the user says "digest bot", "meeting
  digest", "post-meeting summary", "slt digest", or is setting up automated
  SLT broadcast.
---

# SLT Meeting Digest

After every SLT meeting, a 3-bullet digest + action items gets posted to Slack so anyone who missed can catch up in 15 seconds. No more "can someone recap the SLT huddle?"

## Why this exists

Fathom already generates meeting summaries. Problem: they live in Fathom's UI, nobody checks them, and half the SLT routinely misses 1–2 meetings/week due to travel, conflicts, or retreats. Broadcasting the 3-bullet version to Slack closes the gap.

## Architecture — polling, not webhooks

We chose **polling every 15 minutes** over webhook-driven because:
- Webhooks require a publicly-reachable endpoint (Railway / n8n / Cloudflare Worker) — more infra to own
- 15-min latency is fine for "catch up on a meeting you missed"
- Fully self-contained: Windows Task Scheduler + Fathom API + Slack API
- State-tracked via a simple `.last_check` file, so restarts don't miss or duplicate

Webhook version is a future upgrade — the `FATHOM_WEBHOOK_SECRET` is already stashed for it.

## Filter: what counts as an SLT meeting

A meeting is digested if ANY of these are true:
1. Title matches the known patterns: `SLT Huddle`, `SLT Standing`, `SLT Retreat`, `Manager Preview`
2. Invitee list contains ≥2 SLT members (from the hardcoded SLT email list — Kevin, Gary, Adam, Ashleigh, Cory, Michael, Heather)
3. Meeting title contains "SLT" OR "board meeting" (but not "e-board")

Excluded:
- 1:1s (handled by `/pre-meeting-briefing` + close-day)
- Any title matching "Personal" / "Coaching" / "Therapy" / "[Private]" as privacy guard

## Output: the digest format

Posted to Slack as a single message:

```
📋 *{Meeting Title}* — {time} · {duration}m · {attendees}
{Fathom share URL}

*Takeaways*
• {bullet 1 from Fathom summary — shortest form}
• {bullet 2}
• {bullet 3 — max}

*Action items*
• {@mention if we can resolve} {action} — {owner}
```

Single post. Threaded replies could be added later (not today).

## Setup (3 steps)

### 1. Get a Slack bot token (5 min)

Per the `connect` skill (Option B path), create a minimal Slack app at https://api.slack.com/apps:
- Name: `SLT Digest Bot`
- Bot Token Scopes: `chat:write`, `chat:write.public`, `channels:read`
- Install to workspace
- Copy the `xoxb-...` token

Store at `~/.claude/credentials/slt-meeting-digest.env`:
```
SLACK_BOT_TOKEN=xoxb-...
DIGEST_SLACK_CHANNEL=#slt-ops
```

### 2. Invite the bot to the channel

In Slack: `/invite @SLT Digest Bot` in the target channel.

### 3. Schedule the task

```powershell
& "$HOME\.claude\local-plugins\nsls-personal-toolkit\skills\slt-meeting-digest\scripts\schedule_task.ps1"
```

Runs every 15 min.

## Fallback: no Slack token yet

If `SLACK_BOT_TOKEN` is not set, the script **falls back to writing digests to `Obsidian/AP/00-inbox/slt-digest/{timestamp}-{title}.md`** instead of Slack. Anish reviews + manually posts. Proves the pipeline works before committing to a Slack app.

This is intentional — ship working fallback today, upgrade to live Slack once the token lands.

## Safety / guardrails

- **Private meeting filter.** Titles containing `Personal`, `Coaching`, `Therapy`, `[Private]`, or `1:1` are skipped.
- **Dedup.** Each meeting is posted at most once; state tracked in `.posted` file.
- **Rate limit.** Fathom = 60 calls/min; one poll = 1 call. Safe.
- **No automated @mentions** in the first draft. Owner name surfaces as text, not as a resolved Slack user_id — avoids accidental blast to the wrong person.

## Files

| File | Role |
|---|---|
| `SKILL.md` | this |
| `scripts/poll_and_digest.py` | the poller + digester |
| `scripts/schedule_task.ps1` | Windows Task Scheduler (15-min cadence) |

## Related

- `/connect` — Slack setup (Option B) documents the bot-token pattern this skill uses.
- `/pre-meeting-briefing` — separate; handles pre-meeting context, not post-meeting digest.
