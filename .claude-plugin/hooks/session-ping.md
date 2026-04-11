---
name: session-ping
description: Track builder session activity, check for merged PR credits, and deliver toolkit announcements on every session start.
hooks:
  - event: SessionStart
    type: prompt
---

# Session Ping

On session start, ping the automation tracker to:
1. Track this session (daily point, usage stats)
2. Check for uncredited merged PRs
3. Deliver any pending announcements

## Execution

### 1. Gather builder info

Read builder email from one of:
- `~/.claude/local-plugins/nsls-personal-toolkit/.env` (look for `BUILDER_EMAIL`)
- `git config user.email`

Read GitHub username from:
- `~/.claude/local-plugins/nsls-personal-toolkit/.env` (look for `GITHUB_USERNAME`)
- `git config user.name` (may not match GitHub — best effort)

If no email can be found, skip silently. Do not ask the builder.

### 2. Detect installed toolkits

Check which plugins are installed:
- Builder toolkit: check if `~/.claude/local-plugins/nsls-builder-toolkit/` or `~/nsls-skills/nsls-builder-toolkit/` exists
- Personal toolkit: this hook is running, so yes

Set `toolkit` to `"both"` if builder toolkit is found, otherwise `"personal"`.

### 3. Ping the proxy

Call via curl:

```bash
curl -s --max-time 3 -X POST https://web-production-6281e.up.railway.app/session-ping \
  -H 'Content-Type: application/json' \
  -d '{"builder_email": "<email>", "toolkit": "<toolkit>", "github_username": "<username>"}'
```

### 4. Handle the response

**If `new_pr_credits` is non-empty:**
For each credited PR:
> "Your PR [pr] to [repo] was merged — nice work."

**If `stage_advanced` is non-null:**
> "You've advanced to **[to]** status on the builder path."

**If `announcements` is non-empty:**
For each announcement:
> "[title]: [body]"

Then dismiss each:
```bash
curl -s --max-time 3 -X POST https://web-production-6281e.up.railway.app/dismiss-announcement \
  -H 'Content-Type: application/json' \
  -d '{"announcement_id": "<id>", "builder_email": "<email>"}'
```

### 5. Fail silently

If the proxy is unreachable or any step fails — skip silently. This hook must never block or slow down the session. Use `--max-time 3` to cap at 3 seconds.
