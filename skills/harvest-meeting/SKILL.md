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

## Step 0: Mode dispatch + SLT allowlist gate

Parse arguments to determine mode (`--date`, `--fathom-url`, or `--week-audit`).

Then check whether the current user is an SLT writer:

```bash
PYTHONPATH=/tmp/pptx_deps python3.12 -c "
import os, subprocess, sys, pathlib

skill_dir = pathlib.Path(__file__).resolve().parent if '__file__' in dir() else pathlib.Path('$HOME/nsls-skills/nsls-personal-toolkit/skills/harvest-meeting')
authors_file = skill_dir / 'kb_authors.txt'

# Try multiple resolution paths in case the symlink/install path differs
candidates = [
    pathlib.Path.home() / 'nsls-skills/nsls-personal-toolkit/skills/harvest-meeting/kb_authors.txt',
    pathlib.Path.home() / '.claude/plugins/nsls-personal-toolkit/skills/harvest-meeting/kb_authors.txt',
]
authors_file = next((p for p in candidates if p.exists()), None)
if not authors_file:
    print('FATAL: kb_authors.txt not found in any known path')
    sys.exit(2)

user_email = subprocess.check_output(['git', 'config', 'user.email'], text=True).strip()
authors = {line.strip() for line in authors_file.read_text().splitlines()
           if line.strip() and not line.startswith('#')}

is_slt = user_email in authors
print(f'user: {user_email}')
print(f'slt_writer: {is_slt}')
print(f'authors_file: {authors_file}')
"
```

**Heartbeat the result** (per the skill-heartbeats rule):

- If `slt_writer: True` → "Step 0: SLT writer confirmed ({user_email}), proceeding."
- If `slt_writer: False` AND mode is `--date` or `--fathom-url` → "Step 0: not in KB_AUTHORS, skipping harvest." Exit cleanly with `WRITE_AUTHORIZED=false`.
- If `slt_writer: False` AND mode is `--week-audit` → "Step 0: not in KB_AUTHORS, running audit-only (no write actions)." Continue with `WRITE_AUTHORIZED=false`.

Pass `WRITE_AUTHORIZED` (True/False) through to subsequent steps; they consult it to decide whether to execute write actions.
