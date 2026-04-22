# Sharing Surfaces Audit

**Last updated:** 2026-04-21

This document inventories every installed skill's capability to route data **off-device** (to Slack, Google Drive, GitHub, Airtable, email, public web, etc.). Use this to audit the blast radius before invoking skills with sensitive data in scope.

---

## Governance rule

> **Rippling employee data (comp, addresses, benefits, manager chain, tax/compliance) is user-local PII.** It must never be routed through any skill listed in the "Write / Share" column below without explicit user confirmation in the chat.

See also: `~/AppData/Local/nsls-private/rippling/README.md` for the full data-handling policy.

---

## Skills in `nsls-personal-toolkit`

| Skill | Reads | Writes Locally | Shares Externally | Notes |
|-------|-------|----------------|-------------------|-------|
| `open-day` | Gmail, Airtable (SLT tasks), Obsidian vault, Google Calendar, builder profile | Obsidian vault (`01-daily/YYYY-MM-DD.md`), Google Calendar events | ⚠ **Creates calendar events** (visible to attendees if invited; default is solo) | Uses `sendUpdates: "none"` — but still writes to Google Calendar |
| `close-day` | Gmail, Fathom, Airtable, Obsidian vault | Obsidian vault (`01-daily/`) | None | Pure read + local write |
| `open-week` / `close-week` | Obsidian vault, Airtable, Gmail | Obsidian vault (`02-weekly/`) | None | Local-only |
| `log` | Claude conversation | Obsidian vault (`01-daily/` or project log) | None | Local-only |
| `person-intelligence` | Fathom, Airtable SLT, Airtable People Ops, **Rippling cache (when present)**, Obsidian vault, Gmail, Slack | Obsidian vault (`30-people/*.md`), SLT profile folder | None by default | ⚠ **HIGH-RISK for Rippling data.** Default behavior: does NOT write Rippling comp/benefits/addresses into `30-people/` profiles. Opt-in per-person only; if opted in, routes to `50-hr-sensitive/` folder (gitignored) |
| `familiar` | Obsidian vault, Airtable | Obsidian vault | None | Local-only |
| `learn` | Obsidian vault | Obsidian vault (`40-learning/`) | None | Local-only |
| `self-insight` | Obsidian vault | Obsidian vault (`10-strategy/operating-memo.md`) | None | Local-only |
| `obsidian-setup` | Filesystem | Obsidian vault structure | None | Local-only |
| `personal-setup` | `.env`, MCP tools, filesystem | `.env`, Obsidian vault structure | None | Writes API tokens to `.env` — treat `.env` as secret |

---

## Skills in `nsls-builder-toolkit` (org-level, may have broader share reach)

| Skill | Writes / Shares | Risk to Rippling data |
|-------|-----------------|------------------------|
| `slack` | `slack_send_message`, `slack_create_canvas`, `slack_update_canvas` | 🚨 **HIGH** — any Slack send routes data to NSLS workspace |
| `gws` | Google Docs / Sheets / Slides / Drive / Gmail / Calendar (reads **and writes**) | 🚨 **HIGH** — can create Google Docs visible to anyone the doc is shared with |
| `google-drive` | Upload, share, create folders | 🚨 **HIGH** — uploads to Drive; sharing permissions apply |
| `nsls-slides` / `google-slides-api` | Creates/edits Google Slides | 🚨 **MEDIUM** — slides live in Drive, sharable |
| `airtable` | Writes to Airtable bases (accessible to NSLS team with base access) | 🚨 **HIGH** — Airtable writes are visible to all NSLS users with that base |
| `customerio` | Writes campaign data (Customer.io has PII by design) | 🟡 MEDIUM — data goes to member-facing systems |
| `n8n` | Deploys automation workflows on NSLS cloud | 🚨 **HIGH** — workflows run in shared cloud; stored credentials and data accessible to Kevin / tech team |
| `netlify-deploy` | Publishes HTML publicly on the web | 🚨 **CRITICAL** — public web, no access control |
| `hubspot` | Reads 6.9M contacts (read-only per skill doc) | 🟢 LOW — read-only currently, but could be extended to write |
| `posthog` | Creates insights, feature flags, experiments | 🟡 MEDIUM — analytics platform; dashboards visible to PostHog users |
| `braintrust-evals` | Writes evaluation experiments, datasets | 🟡 MEDIUM — Braintrust org-accessible |
| `fathom` | Read-only per MCP | 🟢 LOW |
| `web-research` | Google AI Mode queries | 🟡 MEDIUM — queries go to Google; avoid putting PII in queries |

---

## Skills in `anthropic-skills`

| Skill | Writes / Shares |
|-------|-----------------|
| `pptx`, `pdf`, `docx`, `xlsx` | Local file writes only |
| `schedule` | Creates scheduled tasks in Claude Code runtime (local to your account) |
| `setup-cowork` | Local plugin install |
| `skill-creator` | Local skill file writes |
| `consolidate-memory` | Writes to your auto-memory dir (local) |

---

## Skills in `superpowers`

Generally **process/workflow skills** (brainstorming, TDD, debugging, code review) — they don't have direct share capability but they invoke sub-agents that may. Any sub-agent spawned inherits the blast radius of its tools.

---

## Rules for handling Rippling data

1. **Never** invoke `slack_send_message`, `slack_create_canvas`, `gws`, `google-drive`, `airtable` (write), `n8n`, `netlify-deploy`, or `customerio` with Rippling data in scope without explicit user confirmation.
2. **Never** write Rippling comp/benefits/addresses into the Obsidian vault by default. Opt-in per-person only, routed to `50-hr-sensitive/` folder.
3. **Never** put Rippling data in a `web-research` query, a Braintrust experiment, or a PostHog insight.
4. **Always** prefer the user-local cache at `%LOCALAPPDATA%\nsls-private\rippling\` as the exclusive source of truth.
5. **Before every tool call** that could route data off-device, the AI agent must verify Rippling data is not in the payload. The auto-memory entry `feedback_rippling_governance.md` enforces this.

---

## If you suspect a leak

1. Rotate Rippling API token (Rippling admin → API Keys → Revoke → Generate new)
2. Rotate any other keys that share the exposure path (Airtable PAT, Fathom key, Slack token)
3. Delete local cache at `%LOCALAPPDATA%\nsls-private\rippling\`
4. Check git history in both toolkit repos for accidentally-committed `.env` or cache files:
   ```
   git log --all --full-history -- "**/.env" "**/employees.json" "**/compensation.json"
   ```
5. If committed, rotate keys + consider the repo history compromised (force-push rewrite + contact GitHub about secret scanning).
