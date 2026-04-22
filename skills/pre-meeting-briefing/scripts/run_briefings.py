"""Pre-meeting briefing orchestrator.

Pulls today's meetings from Fathom (as a proxy for calendar — every real meeting gets a Fathom record)
OR from a manually-provided list, then invokes Claude CLI per meeting to generate briefings.

Usage:
  # Generate briefings for today's meetings (from Gmail calendar)
  python run_briefings.py --today

  # Generate a single briefing on demand
  python run_briefings.py --email kprentiss@nsls.org --title "Kevin/Anish" --when "2026-04-24 15:00"

  # Look-ahead mode: tomorrow's meetings
  python run_briefings.py --tomorrow
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
PROMPT_PATH = SKILL_DIR / "briefing_prompt.md"
OBSIDIAN_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", Path.home() / "Obsidian" / "AP"))
OUT_DIR = OBSIDIAN_ROOT / "00-inbox" / "pre-meeting"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = OUT_DIR / ".run.log"
MAX_PARALLEL = int(os.environ.get("BRIEFING_MAX_PARALLEL", "3"))
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def load_env_file(path: Path) -> None:
    """Read simple KEY=VALUE lines from a local .env and set them in os.environ."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

# Credentials are user-local (NOT in the plugin repo).
# Primary location: ~/.claude/credentials/pre-meeting-briefing.env
# Fallback (dev): SKILL_DIR/.env  (gitignored)
load_env_file(Path.home() / ".claude" / "credentials" / "pre-meeting-briefing.env")
load_env_file(SKILL_DIR / ".env")

# SLT email allow-list (expand as needed)
SLT_EMAILS = {
    "kprentiss@nsls.org":     "Kevin Prentiss",
    "gtuerack@nsls.org":      "Gary Tuerack",
    "astone@nsls.org":        "Adam Stone",
    "asmith@nsls.org":        "Ashleigh Smith",
    "ccapoccia@nsls.org":     "Cory Capoccia",
    "cory.capoccia@gmail.com":"Cory Capoccia",
    "mobrien@nsls.org":       "Michael O'Brien",
    "hdarnell@nsls.org":      "Heather Darnell",
    "jfontanez@nsls.org":     "Jenna Fontanez",
    "cbyers@nsls.org":        "Chelsea Byers",
    "jtannenbaum@nsls.org":   "Jordan Tannenbaum",
}

def safe_slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in s).strip("-")

def briefing_path(when_iso: str, person_name: str) -> Path:
    dt = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
    return OUT_DIR / f"{dt.strftime('%Y-%m-%d-%H%M')}-{safe_slug(person_name)}.md"

def _log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{stamp}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def run_claude(prompt: str, output_path: Path) -> tuple[int, str]:
    """Invoke Claude CLI in non-interactive mode with the briefing prompt.
    Returns (exit_code, error_summary). Handles timeouts and missing executables cleanly."""
    claude_exe = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude.exe")
    if not Path(claude_exe).exists():
        return 127, f"claude CLI not found at {claude_exe}"
    cmd = [
        claude_exe,
        "-p", prompt,
        "--output-format", "text",
        "--permission-mode", "bypassPermissions",
        "--add-dir", str(OBSIDIAN_ROOT),
        "--add-dir", str(Path.home() / ".claude" / ".mcp-servers" / "fathom"),
        "--model", "claude-sonnet-4-6",
    ]
    _log(f"  -> invoking Claude for {output_path.name}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after 600s ({output_path.name})"
    except FileNotFoundError as e:
        return 127, f"exec not found: {e}"
    if result.returncode != 0:
        return result.returncode, f"claude exited {result.returncode}: {result.stderr[:500]}"
    return 0, ""

def fetch_gmail_block(person_email: str, days: int = 14) -> str:
    """Run fetch_gmail.py and return the markdown block (empty if unavailable)."""
    if not EMAIL_RE.match(person_email):
        return f"**Gmail:** skipped (invalid email format: {person_email!r})."
    py = sys.executable or shutil.which("python") or "python"
    script = str(SCRIPT_DIR / "fetch_gmail.py")
    try:
        result = subprocess.run(
            [py, script, "--email", person_email, "--days", str(days)],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if result.stderr:
            _log(f"  [gmail] {result.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        _log(f"  [gmail] timeout for {person_email}")
    except Exception as e:
        _log(f"  [gmail] fetch failed: {e}")
    return "**Gmail:** not fetched (GMAIL_APP_PASSWORD not set or IMAP error)."


def compose_prompt(person_name: str, person_email: str, meeting_title: str, when_iso: str, output_path: Path) -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        base = f.read()
    gmail_block = fetch_gmail_block(person_email, days=14)
    injected = f"""
# Task parameters
- PERSON_NAME: {person_name}
- PERSON_EMAIL: {person_email}
- MEETING_TITLE: {meeting_title}
- MEETING_WHEN: {when_iso}
- OUTPUT_PATH: {output_path.as_posix()}

# Gmail context (pre-fetched, inline below — use this for the "Live threads > Email" section; DO NOT call Gmail MCP)
{gmail_block}

---

{base}
"""
    return injected

def single_briefing(email: str, title: str, when_iso: str) -> tuple[Path, str]:
    """Generate one briefing. Returns (output_path, status) where status is
    'ok' | 'exists' | 'err:<summary>'."""
    person_name = SLT_EMAILS.get(email, email.split("@")[0])
    out = briefing_path(when_iso, person_name)
    if out.exists():
        _log(f"  [ok] already exists: {out.name}")
        return out, "exists"
    prompt = compose_prompt(person_name, email, title, when_iso, out)
    rc, err = run_claude(prompt, out)
    if rc == 0 and out.exists():
        _log(f"  [ok] wrote {out.name}")
        return out, "ok"
    _log(f"  [err] {err}")
    return out, f"err:{err[:120]}"

def meetings_from_fathom(start_iso: str, end_iso: str):
    """Use the Fathom API as calendar proxy — any meeting that'll be recorded shows as a calendar invitee listing."""
    fathom_path = Path.home() / ".claude" / ".mcp-servers" / "fathom"
    if str(fathom_path) not in sys.path:
        sys.path.insert(0, str(fathom_path))
    from server import list_meetings  # type: ignore
    results = []
    cursor = None
    while True:
        r = list_meetings(limit=50, cursor=cursor, recorded_after=start_iso, recorded_before=end_iso)
        results.extend(r.get("items", []))
        cursor = r.get("next_cursor")
        if not cursor:
            break
    return results

def pick_attendee(invitees, exclude_email="apatel@nsls.org"):
    """For a meeting, pick the SLT member on the invitee list (not Anish)."""
    for inv in invitees:
        email = (inv.get("email") or "").lower()
        if email != exclude_email and email in SLT_EMAILS:
            return email, SLT_EMAILS[email]
    # Fallback: first non-Anish invitee
    for inv in invitees:
        email = (inv.get("email") or "").lower()
        if email != exclude_email and email:
            return email, inv.get("name", email.split("@")[0])
    return None, None

def run_day(day: datetime):
    """Generate briefings for all meetings on a given day (UTC day bounds).
    Runs up to MAX_PARALLEL briefings concurrently; summarizes results at end."""
    start = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    _log(f"Pulling meetings for {day.date()} (UTC)...")
    meetings = meetings_from_fathom(start_iso, end_iso)
    if not meetings:
        _log(f"  no meetings found for {day.date()}")
        return
    _log(f"  found {len(meetings)} meeting(s)")

    queue = []
    seen_people_today = set()
    for m in meetings:
        invitees = m.get("calendar_invitees") or []
        if len(invitees) > 4:
            continue  # skip big group meetings
        title = m.get("meeting_title") or m.get("title") or "(untitled)"
        if any(skip in title for skip in ["SLT Huddle", "SLT Standing", "All Staff"]):
            continue
        email, name = pick_attendee(invitees)
        if not email:
            continue
        # de-dupe: one briefing per person per day
        if email in seen_people_today:
            continue
        seen_people_today.add(email)
        when = m.get("scheduled_start_time") or m.get("recording_start_time")
        _log(f"  queueing: {name} <{email}> for '{title}' @ {when}")
        queue.append((email, title, when))

    if not queue:
        _log("  nothing to brief (all meetings filtered or de-duped)")
        return
    statuses = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(single_briefing, email, title, when): email for email, title, when in queue}
        for fut in as_completed(futures):
            _, status = fut.result()
            statuses.append((futures[fut], status))
    ok = sum(1 for _, s in statuses if s in ("ok", "exists"))
    err = sum(1 for _, s in statuses if s.startswith("err"))
    _log(f"Summary for {day.date()}: {ok}/{len(statuses)} succeeded, {err} errored")
    for email, status in statuses:
        if status.startswith("err"):
            _log(f"  FAILED {email}: {status}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--tomorrow", action="store_true")
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--email")
    ap.add_argument("--title")
    ap.add_argument("--when", help="ISO timestamp or YYYY-MM-DD HH:MM")
    args = ap.parse_args()

    if args.email:
        if not args.when:
            args.when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            # Normalize
            try:
                dt = datetime.fromisoformat(args.when)
            except ValueError:
                dt = datetime.strptime(args.when, "%Y-%m-%d %H:%M")
            args.when = dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt.tzinfo is None else dt.isoformat()
        single_briefing(args.email, args.title or "Ad hoc", args.when)
        return

    now = datetime.now(timezone.utc)
    if args.today:
        run_day(now)
    elif args.tomorrow:
        run_day(now + timedelta(days=1))
    elif args.date:
        run_day(datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc))
    else:
        # Default: generate briefings for today AND tomorrow
        run_day(now)
        run_day(now + timedelta(days=1))

if __name__ == "__main__":
    main()
