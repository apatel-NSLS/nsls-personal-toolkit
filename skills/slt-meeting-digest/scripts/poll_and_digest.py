"""Poll Fathom for recently-completed SLT meetings and post a digest to Slack.

Runs every 15 minutes via Windows Task Scheduler.
State: stores last_check timestamp + set of already-posted recording_ids in JSON.
Fallback: if SLACK_BOT_TOKEN not set, writes digests to Obsidian inbox instead.
"""
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# UTF-8 stdout on Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
OBSIDIAN_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", Path.home() / "Obsidian" / "AP"))
STATE_PATH = SKILL_DIR / ".state.json"
FALLBACK_DIR = OBSIDIAN_ROOT / "00-inbox" / "slt-digest"
LOG_PATH = FALLBACK_DIR / ".run.log"
FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

# Load credentials
for env_path in [
    Path.home() / ".claude" / "credentials" / "slt-meeting-digest.env",
    SKILL_DIR / ".env",
]:
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

# Also read FATHOM_API_KEY from settings.json if not set
if not os.environ.get("FATHOM_API_KEY"):
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            s = json.loads(settings_path.read_text(encoding="utf-8"))
            key = s.get("mcpServers", {}).get("fathom", {}).get("env", {}).get("FATHOM_API_KEY")
            if key:
                os.environ["FATHOM_API_KEY"] = key
        except Exception:
            pass

FATHOM_API_KEY = os.environ.get("FATHOM_API_KEY", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
DIGEST_SLACK_CHANNEL = os.environ.get("DIGEST_SLACK_CHANNEL", "#slt-ops")

SLT_EMAILS = {
    "kprentiss@nsls.org", "gtuerack@nsls.org", "astone@nsls.org",
    "asmith@nsls.org", "mobrien@nsls.org", "ccapoccia@nsls.org",
    "cory.capoccia@gmail.com", "hdarnell@nsls.org", "jfontanez@nsls.org",
    "cbyers@nsls.org", "jtannenbaum@nsls.org",
}
SLT_TITLE_PATTERNS = [
    r"\bslt\b", r"slt huddle", r"slt standing", r"slt retreat",
    r"manager preview", r"board meeting", r"advisory board",
]
PRIVATE_PATTERNS = [
    r"1:1", r"personal", r"coaching", r"therapy", r"\[private\]",
    r"1-on-1", r"1 on 1", r"/ap$", r"ap /", r"/anish$",
]
ACTION_PREFIX_EMOJIS = ("- [**", "- **")


def _log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{stamp}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_check": None, "posted": []}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def http_get_json(url: str, headers: dict, timeout: int = 30) -> dict:
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def http_post_json(url: str, headers: dict, body: dict, timeout: int = 30) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_recent_meetings(since_iso: str) -> list[dict]:
    """Fetch meetings recorded since `since_iso`. Paginate."""
    headers = {"X-Api-Key": FATHOM_API_KEY}
    base = "https://api.fathom.ai/external/v1/meetings"
    params = {"recorded_after": since_iso, "limit": 50, "include_summary": "true", "include_action_items": "true"}
    results = []
    cursor = None
    for _ in range(10):  # safety cap
        if cursor:
            params["cursor"] = cursor
        q = urlencode(params)
        try:
            data = http_get_json(f"{base}?{q}", headers)
        except HTTPError as e:
            _log(f"fathom HTTP {e.code}: {e.reason}")
            break
        except URLError as e:
            _log(f"fathom URL error: {e}")
            break
        results.extend(data.get("items", []))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return results


def is_slt_meeting(m: dict) -> bool:
    title = (m.get("meeting_title") or m.get("title") or "").lower()
    # Private filter first
    for pat in PRIVATE_PATTERNS:
        if re.search(pat, title):
            return False
    # Title pattern match
    for pat in SLT_TITLE_PATTERNS:
        if re.search(pat, title):
            return True
    # Invitee match — 2+ SLT members
    invitees = m.get("calendar_invitees") or []
    slt_invitees = sum(1 for i in invitees if (i.get("email") or "").lower() in SLT_EMAILS)
    return slt_invitees >= 2


def format_digest(m: dict) -> tuple[str, str]:
    """Return (short_title, message_body)."""
    title = m.get("meeting_title") or m.get("title") or "(untitled)"
    start = m.get("scheduled_start_time") or m.get("recording_start_time") or ""
    duration_min = ""
    end = m.get("scheduled_end_time") or m.get("recording_end_time") or ""
    try:
        if start and end:
            sdt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            edt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration_min = f"{int((edt - sdt).total_seconds() // 60)}m"
    except Exception:
        pass
    attendees = [i.get("name", "") for i in (m.get("calendar_invitees") or [])][:6]
    share = m.get("share_url") or m.get("url") or ""
    summary_md = ((m.get("default_summary") or {}).get("markdown_formatted") or "").strip()
    # Extract 3 most-distinctive bullets (ones prefixed with - [** or - **)
    bullets = []
    for line in summary_md.splitlines():
        s = line.strip()
        if s.startswith(ACTION_PREFIX_EMOJIS):
            cleaned = s.lstrip("- ")
            # Fathom summaries wrap headlines as [**text**](url). Drop the URL, keep **text**.
            cleaned = re.sub(r"\[\*\*([^\]]+?)\*\*\]\([^)]+\)", r"**\1**", cleaned)
            # Clean any stragglers: **text**](url) → **text**
            cleaned = re.sub(r"\*\*\]\([^)]+\)", "**", cleaned)
            # Strip Slack-incompatible inline markdown
            cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
            bullets.append(cleaned)
        if len(bullets) >= 3:
            break
    # Action items
    actions = [a.get("description", "") for a in (m.get("action_items") or []) if a.get("description")]

    lines = [
        f":clipboard: *{title}* — {start[:16].replace('T', ' ')}" + (f" · {duration_min}" if duration_min else ""),
    ]
    if attendees:
        lines.append(f"_With:_ {', '.join(attendees)}")
    if share:
        lines.append(share)
    lines.append("")
    if bullets:
        lines.append("*Takeaways*")
        for b in bullets:
            lines.append(f"• {b}")
    if actions:
        lines.append("")
        lines.append("*Action items*")
        for a in actions[:6]:
            lines.append(f"• {a[:240]}")
    lines.append("")
    lines.append("_Auto-digest by slt-meeting-digest · reply in thread if this missed something._")
    return title, "\n".join(lines)


def post_to_slack(channel: str, text: str) -> tuple[bool, str]:
    """Post to Slack via chat.postMessage. Returns (ok, error_or_ts)."""
    if not SLACK_BOT_TOKEN:
        return False, "SLACK_BOT_TOKEN not set"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    try:
        resp = http_post_json(
            "https://slack.com/api/chat.postMessage",
            headers, {"channel": channel, "text": text},
        )
    except Exception as e:
        return False, f"slack exception: {e}"
    if not resp.get("ok"):
        return False, f"slack error: {resp.get('error')}"
    return True, resp.get("ts", "")


def write_fallback(meeting_id: int, title: str, body: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9\-]", "-", title)[:60].strip("-") or "untitled"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    path = FALLBACK_DIR / f"{stamp}-{meeting_id}-{safe}.md"
    # Strip Slack-specific emoji/format for markdown friendliness
    md = body.replace(":clipboard:", "📋")
    path.write_text(md, encoding="utf-8")
    return path


def main():
    if not FATHOM_API_KEY:
        _log("[err] FATHOM_API_KEY not set — check settings.json mcpServers.fathom.env")
        sys.exit(1)
    state = load_state()
    # First run: look back 2 hours. Steady state: last_check.
    now = datetime.now(timezone.utc)
    since = state.get("last_check") or (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _log(f"polling meetings since {since}")
    try:
        meetings = fetch_recent_meetings(since)
    except Exception as e:
        _log(f"[err] fetch failed: {e}")
        sys.exit(1)
    if not meetings:
        _log("no meetings since last check")
        state["last_check"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        save_state(state)
        return
    _log(f"found {len(meetings)} recent meeting(s)")
    posted_ids = set(state.get("posted", []))
    newly_posted = []
    for m in meetings:
        rid = m.get("recording_id")
        if not rid or rid in posted_ids:
            continue
        if not is_slt_meeting(m):
            continue
        # Skip if summary isn't ready yet (Fathom takes a few minutes)
        summary_md = ((m.get("default_summary") or {}).get("markdown_formatted") or "").strip()
        if not summary_md:
            _log(f"  skipping {rid} (summary not ready)")
            continue
        title, body = format_digest(m)
        ok, info = post_to_slack(DIGEST_SLACK_CHANNEL, body)
        if ok:
            _log(f"  posted {rid} '{title[:60]}' -> Slack ts={info}")
        else:
            path = write_fallback(rid, title, body)
            _log(f"  wrote fallback for {rid} '{title[:60]}' -> {path.name} ({info})")
        newly_posted.append(rid)
    # Retention on posted list — keep last 500
    posted_ids.update(newly_posted)
    state["posted"] = list(posted_ids)[-500:]
    state["last_check"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    save_state(state)
    _log(f"done. {len(newly_posted)} new digest(s) {'posted' if SLACK_BOT_TOKEN else 'written to fallback'}")


if __name__ == "__main__":
    main()
