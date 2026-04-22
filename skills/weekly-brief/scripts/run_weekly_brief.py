"""Weekly brief orchestrator — Sunday 7 PM synthesis agent.

Usage:
  python run_weekly_brief.py                  # this week (mon-sun containing today)
  python run_weekly_brief.py --week 2026-W17  # specific ISO week
  python run_weekly_brief.py --dry-run        # don't invoke claude, just print what would be sent
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
PROMPT_PATH = SKILL_DIR / "brief_prompt.md"
OBSIDIAN_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", Path.home() / "Obsidian" / "AP"))
DAILY_DIR = OBSIDIAN_ROOT / "01-daily"
WEEKLY_DIR = OBSIDIAN_ROOT / "02-weekly"
WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
PRE_MEETING_DIR = OBSIDIAN_ROOT / "00-inbox" / "pre-meeting"
LOG_PATH = WEEKLY_DIR / ".run.log"


def _log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{stamp}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def iso_week_bounds(week_label: str) -> tuple[date, date]:
    """Given '2026-W17' return (Monday-date, Sunday-date) of that ISO week."""
    year, wnum = week_label.split("-W")
    monday = date.fromisocalendar(int(year), int(wnum), 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def current_week_label(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def read_daily_notes(start: date, end: date) -> str:
    """Concatenate daily notes for the given range, labeled by date."""
    out = []
    d = start
    while d <= end:
        path = DAILY_DIR / f"{d.isoformat()}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace")
            out.append(f"### Daily note — {d.isoformat()}\n\n{content}\n")
        d += timedelta(days=1)
    return "\n\n".join(out) if out else "(no daily notes found for this week)"


def read_pre_meeting_briefings(start: date, end: date) -> str:
    """List pre-meeting briefings generated for this week (so we know 1:1 attendance)."""
    if not PRE_MEETING_DIR.exists():
        return "(no pre-meeting dir)"
    hits = []
    d = start
    while d <= end:
        prefix = d.isoformat()
        for f in PRE_MEETING_DIR.glob(f"{prefix}*.md"):
            hits.append(f.name)
        d += timedelta(days=1)
    return "\n".join(f"- {h}" for h in sorted(hits)) if hits else "(no briefings generated this week)"


def fetch_fathom_meetings(start: date, end: date) -> str:
    """Use the Fathom MCP server's Python module directly (same pattern as pre-meeting-briefing)."""
    fathom_path = Path.home() / ".claude" / ".mcp-servers" / "fathom"
    if not fathom_path.exists():
        return "(Fathom MCP not installed)"
    if str(fathom_path) not in sys.path:
        sys.path.insert(0, str(fathom_path))
    try:
        from server import list_meetings  # type: ignore
    except Exception as e:
        return f"(Fathom import failed: {e})"
    start_iso = f"{start.isoformat()}T00:00:00Z"
    end_iso = f"{end.isoformat()}T23:59:59Z"
    try:
        results = []
        cursor = None
        while True:
            r = list_meetings(limit=50, cursor=cursor, recorded_after=start_iso, recorded_before=end_iso, include_summary=True)
            results.extend(r.get("items", []))
            cursor = r.get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        return f"(Fathom fetch failed: {e})"
    if not results:
        return "(no Fathom meetings this week)"
    out = []
    for m in sorted(results, key=lambda x: x.get("scheduled_start_time", "")):
        title = m.get("meeting_title") or m.get("title") or "(untitled)"
        when = (m.get("scheduled_start_time") or "")[:16]
        attendees = [i.get("name", "?") for i in (m.get("calendar_invitees") or [])][:5]
        summary_md = ((m.get("default_summary") or {}).get("markdown_formatted") or "").strip()
        summary_lines = [l for l in summary_md.splitlines() if l.strip().startswith("- [**") or l.strip().startswith("- **")][:3]
        block = [f"**{title}** — {when}", f"  With: {', '.join(attendees)}"]
        if summary_lines:
            block.extend(f"  {l.strip()}" for l in summary_lines)
        out.append("\n".join(block))
    return "\n\n".join(out)


def compose_prompt(week_label: str, start: date, end: date, output_path: Path) -> str:
    base = PROMPT_PATH.read_text(encoding="utf-8")
    daily = read_daily_notes(start, end)
    fathom = fetch_fathom_meetings(start, end)
    briefings = read_pre_meeting_briefings(start, end)
    return f"""
# Task parameters
- WEEK_LABEL: {week_label}
- WEEK_START: {start.isoformat()}
- WEEK_END: {end.isoformat()}
- OUTPUT_PATH: {output_path.as_posix()}
- OBSIDIAN_ROOT: {OBSIDIAN_ROOT.as_posix()}

# DAILY_NOTES (pre-fetched, inlined below — use these directly, do NOT re-read)

{daily}

---

# FATHOM_MEETINGS (pre-fetched summaries — do NOT re-fetch)

{fathom}

---

# PRE_MEETING_BRIEFINGS generated this week

{briefings}

---

{base}
"""


def run_claude(prompt: str, output_path: Path) -> int:
    claude_exe = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude.exe")
    cmd = [
        claude_exe, "-p", prompt,
        "--output-format", "text",
        "--permission-mode", "bypassPermissions",
        "--add-dir", str(OBSIDIAN_ROOT),
        "--model", "claude-sonnet-4-6",
    ]
    _log(f"  -> invoking Claude for {output_path.name}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        _log(f"  [err] timeout")
        return 124
    if r.returncode != 0:
        _log(f"  [err] claude exited {r.returncode}: {r.stderr[:300]}")
    else:
        _log(f"  [ok] wrote {output_path.name}")
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", help="ISO week like 2026-W17; defaults to current")
    ap.add_argument("--dry-run", action="store_true", help="print prompt length, do not invoke Claude")
    args = ap.parse_args()

    today = date.today()
    week = args.week or current_week_label(today)
    start, end = iso_week_bounds(week)
    output_path = WEEKLY_DIR / f"{week}-brief.md"

    if output_path.exists():
        _log(f"  [ok] already exists: {output_path.name}")
        return

    prompt = compose_prompt(week, start, end, output_path)
    _log(f"Composed prompt for {week} ({start} to {end}): {len(prompt):,} chars")

    if args.dry_run:
        print(prompt[:2000])
        print(f"... (truncated; total {len(prompt):,} chars)")
        return

    run_claude(prompt, output_path)


if __name__ == "__main__":
    main()
