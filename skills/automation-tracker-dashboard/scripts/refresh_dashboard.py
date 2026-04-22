"""Refresh Obsidian automations-dashboard.md from the Automation Tracker API.

Usage: python refresh_dashboard.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

API_BASE = "https://web-production-6281e.up.railway.app"
OBSIDIAN_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", Path.home() / "Obsidian" / "AP"))
OUT_PATH = OBSIDIAN_ROOT / "03-meta" / "automations-dashboard.md"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
BUILDER_EMAIL = os.environ.get("BUILDER_EMAIL", "apatel@nsls.org")


def api_get(path: str, timeout: int = 20):
    req = Request(f"{API_BASE}{path}", headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def by_stage(automations):
    buckets = {}
    for a in automations:
        buckets.setdefault(a.get("stage", "?"), []).append(a)
    return buckets


def by_department(automations):
    buckets = {}
    for a in automations:
        dept = a.get("department") or "(unassigned)"
        buckets.setdefault(dept, []).append(a)
    return {k: sorted(v, key=lambda x: x.get("name") or "") for k, v in sorted(buckets.items())}


def by_type(automations):
    counts = {}
    for a in automations:
        counts[a.get("type", "?")] = counts.get(a.get("type", "?"), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def render(automations_resp, stats_resp) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    automations = automations_resp.get("records") or []
    total = automations_resp.get("count") or len(automations)
    stages = by_stage(automations)
    departments = by_department(automations)
    types = by_type(automations)

    builder = stats_resp.get("builder") or {}
    my_automations = stats_resp.get("automations") or []
    recent_events = (stats_resp.get("recent_events") or [])[:10]

    lines = [
        "---",
        "type: dashboard",
        f"generated: {now}",
        "source: web-production-6281e.up.railway.app/automations",
        "---",
        "",
        "# NSLS Automation Tracker — Dashboard",
        "",
        f"*Auto-refreshed {now}. Edit the upstream Airtable to change anything; this page is a mirror.*",
        "",
        "## Portfolio at a glance",
        "",
        f"- **Total automations tracked:** {total}",
    ]
    for stage in ["Prototype", "Production", "Org-Owned"]:
        lines.append(f"- **{stage}:** {len(stages.get(stage, []))}")
    lines.append("")
    lines.append("### By type")
    for t, c in types.items():
        lines.append(f"- {t}: {c}")
    lines.append("")

    # Anish's automations
    lines.append(f"## {builder.get('name', 'Builder')}'s automations")
    lines.append("")
    lines.append(f"- **Stage:** {builder.get('stage', '?')}")
    lines.append(f"- **Points total:** {builder.get('points_total', 0)}")
    lines.append("")
    if my_automations:
        lines.append("| Name | Stage | Checklist | Remaining |")
        lines.append("|------|-------|-----------|-----------|")
        for a in my_automations:
            done = a.get("checklist_complete", 0)
            total_items = a.get("checklist_total", 12)
            remaining = a.get("checklist_remaining") or []
            pct = f"{done}/{total_items}"
            rem_short = ", ".join(remaining[:3]) + (f" +{len(remaining)-3} more" if len(remaining) > 3 else "")
            lines.append(f"| **{a['name']}** | {a.get('stage','?')} | {pct} | {rem_short or '—'} |")
    else:
        lines.append("*(no automations owned yet)*")
    lines.append("")

    # Recent events
    if recent_events:
        lines.append("## Recent builder activity")
        lines.append("")
        for e in recent_events[:8]:
            when = e.get("created", "")[:10]
            desc = e.get("description", "")
            pts = e.get("points", "")
            lines.append(f"- `{when}` {desc} *(+{pts})*")
        lines.append("")

    # Ready to advance
    ready = []
    for a in automations:
        if a.get("stage") != "Prototype":
            continue
        # We don't have checklist totals here; use name-based heuristic — owners of automations
        # with descriptions hinting at production-readiness could be surfaced from builder-stats
        # in a future enhancement. For now just flag SLT-department Prototypes as nudges.
        if a.get("department") in ("Leadership (SLT)", "Finance"):
            ready.append(a)
    if ready:
        lines.append("## SLT/Finance Prototypes to watch")
        lines.append("")
        for a in ready:
            lines.append(f"- **{a['name']}** ({a.get('department')}) — {a.get('description','')[:160]}")
        lines.append("")

    # Full portfolio by department
    lines.append("## Full portfolio by department")
    lines.append("")
    for dept, items in departments.items():
        lines.append(f"### {dept}")
        for a in items:
            lines.append(f"- **{a['name']}** — *{a.get('stage','?')}* · {a.get('scope','?')} · {a.get('type','?')}")
            desc = (a.get("description") or "")[:200]
            if desc:
                lines.append(f"  {desc}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main():
    try:
        automations = api_get("/automations")
        stats = api_get(f"/builder-stats/{BUILDER_EMAIL}")
    except URLError as e:
        sys.stderr.write(f"API unreachable: {e}\n")
        sys.exit(1)
    content = render(automations, stats)
    OUT_PATH.write_text(content, encoding="utf-8")
    print(f"wrote {OUT_PATH}  ({len(content):,} chars)")


if __name__ == "__main__":
    main()
