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

## Step 1: Load context

For `--date` and `--fathom-url` modes, load:
1. KB local clone (refresh first), topic file index, rubric
2. Current Fathom meeting data (Step 2 builds on this)

For `--week-audit` mode, load KB local clone + git log for the week (Task 11 fills this in).

### 1a. Ensure KB local clone is fresh

```bash
KB_DIR="$OBSIDIAN_VAULT_PATH/60-nsls-knowledge"
if [ ! -d "$KB_DIR/.git" ]; then
    echo "Step 1a: FATAL — KB not cloned to $KB_DIR. Run: git clone https://github.com/thensls/nsls-knowledge.git \"$KB_DIR\""
    exit 1
fi
git -C "$KB_DIR" pull --ff-only --quiet
echo "Step 1a: KB synced to $(git -C "$KB_DIR" rev-parse --short HEAD)"
```

### 1b. Load topic index and rubric

```bash
PYTHONPATH=/tmp/pptx_deps python3.12 << 'PYEOF'
import os, pathlib, re, json

kb_dir = pathlib.Path(os.environ['OBSIDIAN_VAULT_PATH']) / '60-nsls-knowledge'

# Parse frontmatter + body for every topic file
topics = {}
for md_file in kb_dir.glob('*.md'):
    if md_file.name.startswith('_'): continue  # _index.md, etc.
    text = md_file.read_text()
    fm_match = re.match(r'^---\n(.*?)\n---\n(.*)$', text, re.DOTALL)
    if not fm_match: continue
    fm_raw, body = fm_match.groups()
    fm = {}
    for line in fm_raw.split('\n'):
        if ':' in line:
            k, _, v = line.partition(':')
            fm[k.strip()] = v.strip()

    # Extract Current State, Key Decisions, Open Questions sections
    sections = {'current_state': '', 'key_decisions': [], 'open_questions': []}
    cur = None
    for line in body.split('\n'):
        if line.startswith('## Current State'): cur = 'current_state'; continue
        if line.startswith('## Key Decisions'): cur = 'key_decisions'; continue
        if line.startswith('## Open Questions'): cur = 'open_questions'; continue
        if line.startswith('## '): cur = None; continue
        if cur == 'current_state':
            sections['current_state'] += line + '\n'
        elif cur in ('key_decisions', 'open_questions') and line.strip().startswith('-'):
            sections[cur].append(line.strip())

    topics[md_file.stem] = {
        'frontmatter': fm,
        'current_state': sections['current_state'].strip(),
        'key_decisions': sections['key_decisions'],
        'open_questions': sections['open_questions'],
    }

# Parse rubric from CLAUDE.md
claude_md = (kb_dir / 'CLAUDE.md').read_text()
rubric_match = re.search(r'## Sensitive-Content Rubric.*?(?=\n## |\Z)', claude_md, re.DOTALL)
rubric_text = rubric_match.group(0) if rubric_match else ''

print(f"Step 1b: loaded {len(topics)} topic files, rubric is {len(rubric_text)} chars")

# Stash for downstream steps
ctx_dir = pathlib.Path('/tmp/harvest-meeting-ctx')
ctx_dir.mkdir(exist_ok=True)
(ctx_dir / 'topics.json').write_text(json.dumps(topics, indent=2))
(ctx_dir / 'rubric.md').write_text(rubric_text)
print(f"Step 1b: cached context at {ctx_dir}")
PYEOF
```

**Heartbeat expected:** `Step 1b: loaded 60 topic files, rubric is ~5000 chars`. If fewer than 40 topic files, something is wrong with the KB clone.
