---
name: harvest-meeting
description: Harvest decisions, project definitions, and state changes from SLT meetings into the NSLS Knowledge Base (60-nsls-knowledge). Gated to SLT writers. Use when you've just finished a strategic meeting, want to backfill a specific Fathom URL, or as part of close-day Step 4c / close-week Step 2b.
---

# Harvest Meeting — NSLS Knowledge Base Pipeline

Pulls decisions, project definitions, and state changes from SLT-recorded meetings, gates them through the employee-facing sensitive-content rubric, and proposes precise edits to topic files in `60-nsls-knowledge`. Approved edits are committed to `main` and pushed.

## Modes

| Mode | When | Source |
|---|---|---|
| `--date YYYY-MM-DD` | close-day Step 4c | All Fathom meetings for the date |
| `--fathom-url <url>` | Manual after important meeting | Single meeting |
| `--week-audit --week YYYY-Www` | close-week Step 2b | Git log + topic files for the week |

## SLT Allowlist

Writes require the current git user.email to be present in `kb_authors.txt` (same directory as this SKILL.md). Non-SLT users running `--week-audit` get the audit report; write actions are silently skipped.

## Step 0: Mode dispatch

Parse arguments. Heartbeat which mode is active. Branch into the appropriate flow below.

(Subsequent steps populated by Tasks 2–9.)
