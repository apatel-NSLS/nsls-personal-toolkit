"""Refresh Obsidian board-tasks dashboard from the SLT Meeting Intelligence Airtable base.

Pulls OPEN tasks that are board-relevant (keyword match excluding e-board noise) OR
that are due before the next 45-day board meeting. Groups by owner. Writes markdown.

Usage: python refresh_board_tasks.py
"""
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

# UTF-8 stdout on Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent

OBSIDIAN_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", Path.home() / "Obsidian" / "AP"))
OUT_PATH = OBSIDIAN_ROOT / "03-meta" / "board-tasks.md"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Next 45-day board meeting. Update as needed.
NEXT_BOARD_MEETING = os.environ.get("NEXT_BOARD_MEETING", "2026-04-27")

# Load .env from personal toolkit
ENV_FILE = Path.home() / ".claude" / "local-plugins" / "nsls-personal-toolkit" / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            if k.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip()

AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
BASE_ID = os.environ.get("AIRTABLE_SLT_BASE_ID", "appHDEHQA4bvlWwQq")
TABLE_ID = os.environ.get("AIRTABLE_TASKS_TABLE_ID", "tblasgjUjadHCqzrg")

BOARD_KEYWORDS = [
    "board meeting", "45-day", "45 day", "board ask", "board prep", "board update",
    "board member", "advisory board", "to the board", "for the board", "board materials",
    "board deck", "board session", "board agenda", "board vote", "board call",
    "board tasks", "board check-in",
]
NEGATIVE_KEYWORDS = ["e-board", "eboard"]  # student chapter boards


def airtable_query(filter_formula: str, page_size: int = 100):
    if not AIRTABLE_PAT:
        raise RuntimeError("AIRTABLE_PAT not set — check .env")
    url = (
        f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
        f"?filterByFormula={quote(filter_formula)}&pageSize={page_size}"
    )
    req = Request(url, headers={"Authorization": f"Bearer {AIRTABLE_PAT}"})
    with urlopen(req, timeout=30) as r:
        return json.load(r).get("records", [])


def is_board_relevant(task: dict) -> bool:
    text = " ".join([
        str(task.get("action_description") or ""),
        str(task.get("action") or ""),
    ]).lower()
    if any(neg in text for neg in NEGATIVE_KEYWORDS):
        return False
    return any(kw in text for kw in BOARD_KEYWORDS)


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def fetch_tasks() -> list[dict]:
    """Pull open tasks that mention board keywords OR are due before next board meeting."""
    next_board = parse_date(NEXT_BOARD_MEETING)
    # Broad query — not-completed OR in-progress
    # We post-filter in Python for keyword precision
    filter_formula = 'OR({status}="Not Started",{status}="In Progress")'
    records = airtable_query(filter_formula)
    out = []
    for r in records:
        f = r.get("fields", {})
        due = parse_date(f.get("due_date"))
        board_relevant = is_board_relevant(f)
        due_before_board = next_board and due and due <= next_board
        if board_relevant or due_before_board:
            out.append({
                "id": r["id"],
                "description": f.get("action_description") or "(no description)",
                "owner": f.get("assignee") or (f.get("User", [{}])[0].get("name") if f.get("User") else None) or "Unassigned",
                "owner_email": f.get("assignee_email") or "",
                "status": f.get("status", ""),
                "due": due,
                "meeting_date": (f.get("meeting_date") or [None])[0] if isinstance(f.get("meeting_date"), list) else f.get("meeting_date"),
                "priority": f.get("Priority", ""),
                "recording_link": f.get("recording_link", ""),
                "board_relevant": board_relevant,
                "due_before_board": bool(due_before_board),
            })
    return out


def render(tasks: list[dict]) -> str:
    today = date.today()
    next_board = parse_date(NEXT_BOARD_MEETING)
    days_to_board = (next_board - today).days if next_board else None
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Split into buckets
    overdue = []
    due_soon = []  # within 7 days
    other = []
    unassigned_date = []
    for t in tasks:
        if t["due"] is None:
            unassigned_date.append(t)
        elif t["due"] < today:
            overdue.append(t)
        elif (t["due"] - today).days <= 7:
            due_soon.append(t)
        else:
            other.append(t)
    for bucket in (overdue, due_soon, other):
        bucket.sort(key=lambda t: (t["due"] or date.max, t["owner"]))

    # Group "other" by owner
    by_owner = defaultdict(list)
    for t in other + unassigned_date:
        by_owner[t["owner"]].append(t)

    lines = [
        "---",
        "type: dashboard",
        f"generated: {generated}",
        f"next_board_meeting: {NEXT_BOARD_MEETING}",
        f"days_to_board: {days_to_board if days_to_board is not None else 'unknown'}",
        "source: airtable-slt-meeting-intelligence",
        "---",
        "",
        "# Board Tasks — Dashboard",
        "",
        f"*Auto-refreshed {generated}. Edit upstream in Airtable; this page mirrors.*",
        "",
        f"**Next 45-day board meeting:** {NEXT_BOARD_MEETING} ({days_to_board} days away)",
        "",
        f"**Total open tasks tracked here:** {len(tasks)} (board-relevant keywords OR due before {NEXT_BOARD_MEETING})",
        "",
    ]

    def render_task(t):
        due_str = t["due"].isoformat() if t["due"] else "no due date"
        flag = ""
        if t["due"]:
            if t["due"] < today:
                flag = " **🔴 OVERDUE**"
            elif (t["due"] - today).days <= 3:
                flag = " **⚠️**"
        status = t.get("status") or ""
        status_str = f" *{status}*" if status and status != "Not Started" else ""
        link = f" [[{t['recording_link']}|fathom]]" if t.get("recording_link") else ""
        who = t["owner"]
        desc = t["description"][:180]
        return f"- [ ] **{who}** — {desc} — due {due_str}{flag}{status_str}{link}"

    if overdue:
        lines += ["## 🔴 Overdue", ""]
        for t in overdue:
            lines.append(render_task(t))
        lines.append("")

    if due_soon:
        lines += ["## ⚠️ Due within 7 days", ""]
        for t in due_soon:
            lines.append(render_task(t))
        lines.append("")

    lines += ["## By owner", ""]
    for owner in sorted(by_owner.keys()):
        lines.append(f"### {owner} ({len(by_owner[owner])})")
        lines.append("")
        for t in by_owner[owner]:
            lines.append(render_task(t))
        lines.append("")

    # Summary footer
    n_relevant = sum(1 for t in tasks if t["board_relevant"])
    n_due = sum(1 for t in tasks if t["due_before_board"] and not t["board_relevant"])
    lines += [
        "---",
        "",
        f"*{n_relevant} tasks matched board keywords. {n_due} additional tasks included because they're due before {NEXT_BOARD_MEETING}.*",
        "",
    ]
    return "\n".join(lines)


def main():
    try:
        tasks = fetch_tasks()
    except Exception as e:
        print(f"[err] airtable fetch failed: {e}", file=sys.stderr)
        sys.exit(1)
    content = render(tasks)
    OUT_PATH.write_text(content, encoding="utf-8")
    print(f"wrote {OUT_PATH}  ({len(content):,} chars, {len(tasks)} tasks)")


if __name__ == "__main__":
    main()
