"""SLT Meeting Digest bot — approval-required flow.

Every 15 min:
  Phase A (Discovery): poll Fathom for new completed SLT meetings → draft a digest
    → DM Anish via Slack (if token configured) AND write to Obsidian pending inbox.
    The digest is NOT posted to any channel yet.
  Phase B (Approval Check): for each pending digest, check if Anish has reacted:
    ✅ in Slack DM → post to DIGEST_TARGET_CHANNEL
    ❌ in Slack DM → mark dismissed
    OR Obsidian file's frontmatter has `approved: true` → post
    OR Obsidian file's frontmatter has `dismissed: true` → mark dismissed
    OR expires after 48h → mark expired (never post)

Nothing goes to a channel without explicit approval. Default is nothing-posts.

Env vars:
  FATHOM_API_KEY          — required, from ~/.claude/settings.json or env
  SLACK_BOT_TOKEN         — optional; without it, pure Obsidian-fallback mode
  SLACK_ANISH_USER_ID     — Anish's Slack user ID (for DM); required if SLACK_BOT_TOKEN set
  DIGEST_TARGET_CHANNEL   — channel name or ID where APPROVED digests go (e.g. #nsls-leadership)
                            If empty, approved digests still just land in Obsidian.
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
OBSIDIAN_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", Path.home() / "Obsidian" / "AP"))
STATE_PATH = SKILL_DIR / ".state.json"
PENDING_DIR = OBSIDIAN_ROOT / "00-inbox" / "slt-digest"
LOG_PATH = PENDING_DIR / ".run.log"
PENDING_DIR.mkdir(parents=True, exist_ok=True)

APPROVAL_EMOJIS = {"white_check_mark", "heavy_check_mark", "+1", "thumbsup", "check", "approve"}
DISMISS_EMOJIS = {"x", "negative_squared_cross_mark", "no_entry", "-1", "thumbsdown"}
EXPIRES_HOURS = 48

# Load credentials from user-local .env
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

# Fathom key from settings.json fallback
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
SLACK_ANISH_USER_ID = os.environ.get("SLACK_ANISH_USER_ID", "")
DIGEST_TARGET_CHANNEL = os.environ.get("DIGEST_TARGET_CHANNEL", "")

SLT_EMAILS = {
    "kprentiss@nsls.org", "gtuerack@nsls.org", "astone@nsls.org",
    "asmith@nsls.org", "mobrien@nsls.org", "ccapoccia@nsls.org",
    "cory.capoccia@gmail.com", "hdarnell@nsls.org", "jfontanez@nsls.org",
    "cbyers@nsls.org", "jtannenbaum@nsls.org",
}
SLT_TITLE_PATTERNS = [r"\bslt\b", r"slt huddle", r"slt standing", r"slt retreat",
                     r"manager preview", r"board meeting", r"advisory board"]
PRIVATE_PATTERNS = [r"1:1", r"personal", r"coaching", r"therapy", r"\[private\]",
                   r"1-on-1", r"1 on 1"]
ACTION_PREFIX = ("- [**", "- **")


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
            s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            # Migrate old format if needed
            if isinstance(s.get("pending"), list):
                s["pending"] = {}
            s.setdefault("pending", {})
            s.setdefault("posted", [])
            s.setdefault("dismissed", [])
            s.setdefault("last_check", None)
            return s
        except Exception:
            pass
    return {"last_check": None, "pending": {}, "posted": [], "dismissed": []}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def http_get(url: str, headers: dict, timeout: int = 30):
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def http_post(url: str, headers: dict, body: dict, timeout: int = 30):
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def slack_post(endpoint: str, body: dict) -> dict:
    if not SLACK_BOT_TOKEN:
        return {"ok": False, "error": "no_token"}
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
               "Content-Type": "application/json; charset=utf-8"}
    try:
        return http_post(f"https://slack.com/api/{endpoint}", headers, body)
    except Exception as e:
        return {"ok": False, "error": f"exception: {e}"}


def slack_get(endpoint: str, params: dict) -> dict:
    if not SLACK_BOT_TOKEN:
        return {"ok": False, "error": "no_token"}
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    try:
        url = f"https://slack.com/api/{endpoint}?{urlencode(params)}"
        return http_get(url, headers)
    except Exception as e:
        return {"ok": False, "error": f"exception: {e}"}


def fetch_recent_meetings(since_iso: str) -> list[dict]:
    headers = {"X-Api-Key": FATHOM_API_KEY}
    base = "https://api.fathom.ai/external/v1/meetings"
    params = {"recorded_after": since_iso, "limit": 50,
             "include_summary": "true", "include_action_items": "true"}
    results = []
    cursor = None
    for _ in range(10):
        if cursor:
            params["cursor"] = cursor
        try:
            data = http_get(f"{base}?{urlencode(params)}", headers)
        except (HTTPError, URLError) as e:
            _log(f"fathom error: {e}")
            break
        results.extend(data.get("items", []))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return results


def is_slt_meeting(m: dict) -> bool:
    title = (m.get("meeting_title") or m.get("title") or "").lower()
    for pat in PRIVATE_PATTERNS:
        if re.search(pat, title):
            return False
    for pat in SLT_TITLE_PATTERNS:
        if re.search(pat, title):
            return True
    invitees = m.get("calendar_invitees") or []
    slt_count = sum(1 for i in invitees if (i.get("email") or "").lower() in SLT_EMAILS)
    return slt_count >= 2


def format_digest(m: dict) -> tuple[str, str]:
    title = m.get("meeting_title") or m.get("title") or "(untitled)"
    start = m.get("scheduled_start_time") or m.get("recording_start_time") or ""
    duration = ""
    end = m.get("scheduled_end_time") or m.get("recording_end_time") or ""
    try:
        if start and end:
            sdt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            edt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration = f"{int((edt - sdt).total_seconds() // 60)}m"
    except Exception:
        pass
    attendees = [i.get("name", "") for i in (m.get("calendar_invitees") or [])][:6]
    share = m.get("share_url") or m.get("url") or ""
    summary_md = ((m.get("default_summary") or {}).get("markdown_formatted") or "").strip()
    bullets = []
    for line in summary_md.splitlines():
        s = line.strip()
        if s.startswith(ACTION_PREFIX):
            c = s.lstrip("- ")
            c = re.sub(r"\[\*\*([^\]]+?)\*\*\]\([^)]+\)", r"**\1**", c)
            c = re.sub(r"\*\*\]\([^)]+\)", "**", c)
            c = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", c)
            bullets.append(c)
        if len(bullets) >= 3:
            break
    actions = [a.get("description", "") for a in (m.get("action_items") or []) if a.get("description")][:6]
    lines = [f":clipboard: *{title}* — {start[:16].replace('T', ' ')}" + (f" · {duration}" if duration else "")]
    if attendees:
        lines.append(f"_With:_ {', '.join(attendees)}")
    if share:
        lines.append(share)
    lines.append("")
    if bullets:
        lines.append("*Takeaways*")
        lines.extend(f"• {b}" for b in bullets)
    if actions:
        lines.append("")
        lines.append("*Action items*")
        lines.extend(f"• {a[:240]}" for a in actions)
    return title, "\n".join(lines)


def write_pending_obsidian(recording_id: int, title: str, body: str, target_channel: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9\-]", "-", title)[:60].strip("-") or "untitled"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    path = PENDING_DIR / f"{stamp}-{recording_id}-{safe}.md"
    md = body.replace(":clipboard:", "📋")
    frontmatter = [
        "---",
        "type: slt-digest-pending",
        f"recording_id: {recording_id}",
        f"target_channel: {target_channel or '(none — digest stays here)'}",
        "approved: false",
        "dismissed: false",
        f"created: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "---",
        "",
        "> **Approval required.** Edit this file and set `approved: true` to post to the target channel, OR `dismissed: true` to drop. OR react ✅/❌ on the Slack DM.",
        "",
    ]
    path.write_text("\n".join(frontmatter) + md, encoding="utf-8")
    return path


def read_obsidian_approval(path: Path) -> str | None:
    """Return 'approve', 'dismiss', or None from the file's frontmatter."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    fm = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm:
        return None
    fm_text = fm.group(1)
    approved = re.search(r"^approved:\s*(true|false)", fm_text, re.MULTILINE | re.IGNORECASE)
    dismissed = re.search(r"^dismissed:\s*(true|false)", fm_text, re.MULTILINE | re.IGNORECASE)
    if approved and approved.group(1).lower() == "true":
        return "approve"
    if dismissed and dismissed.group(1).lower() == "true":
        return "dismiss"
    return None


def check_slack_reactions(channel_id: str, ts: str) -> str | None:
    """Check reactions on a specific DM message. Return 'approve', 'dismiss', or None."""
    resp = slack_get("reactions.get", {"channel": channel_id, "timestamp": ts, "full": "true"})
    if not resp.get("ok"):
        return None
    msg = resp.get("message", {})
    for r in msg.get("reactions", []):
        name = r.get("name", "")
        if name in APPROVAL_EMOJIS:
            return "approve"
        if name in DISMISS_EMOJIS:
            return "dismiss"
    return None


def open_dm_channel(user_id: str) -> str | None:
    resp = slack_post("conversations.open", {"users": user_id})
    if not resp.get("ok"):
        _log(f"  [slack] failed to open DM with {user_id}: {resp.get('error')}")
        return None
    return resp.get("channel", {}).get("id")


def dm_anish(body: str, recording_id: int, obsidian_path: Path, target_channel: str) -> str | None:
    """Send the pending digest to Anish's DM with approval instructions. Return message ts."""
    if not SLACK_BOT_TOKEN or not SLACK_ANISH_USER_ID:
        return None
    channel_id = open_dm_channel(SLACK_ANISH_USER_ID)
    if not channel_id:
        return None
    full = body + "\n\n" + (
        f"_React :white_check_mark: to post to *{target_channel}*, or :x: to drop._\n"
        f"_You can also edit `{obsidian_path.name}` in Obsidian and set `approved: true`._"
        if target_channel
        else f"_No channel target set — this digest will stay in Obsidian only._\n"
             f"_Edit `{obsidian_path.name}` to mark approved/dismissed, or set DIGEST_TARGET_CHANNEL in the .env._"
    )
    resp = slack_post("chat.postMessage", {"channel": channel_id, "text": full})
    if not resp.get("ok"):
        _log(f"  [slack] DM failed: {resp.get('error')}")
        return None
    return resp.get("ts")


def post_to_target_channel(channel: str, body: str) -> tuple[bool, str]:
    if not SLACK_BOT_TOKEN:
        return False, "no_token"
    resp = slack_post("chat.postMessage", {"channel": channel, "text": body})
    if not resp.get("ok"):
        return False, resp.get("error", "unknown")
    return True, resp.get("ts", "")


def discovery_phase(state: dict) -> int:
    """Find new SLT meetings → draft digest → write pending + DM Anish. Return count drafted.

    On first run (last_check is None), only look back 30 minutes — avoids the
    Fathom API quirk where an unbounded `recorded_after` can return much older
    meetings. Steady-state runs at 15-min cadence so 30 min backfill gives 2x
    safety margin on each poll.
    """
    now = datetime.now(timezone.utc)
    since = state.get("last_check") or (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        meetings = fetch_recent_meetings(since)
    except Exception as e:
        _log(f"fetch failed: {e}")
        return 0
    _log(f"found {len(meetings)} recent meeting(s)")
    drafted = 0
    for m in meetings:
        rid = str(m.get("recording_id") or "")
        if not rid:
            continue
        if rid in state["posted"] or rid in state["dismissed"] or rid in state["pending"]:
            continue
        if not is_slt_meeting(m):
            continue
        summary_md = ((m.get("default_summary") or {}).get("markdown_formatted") or "").strip()
        if not summary_md:
            _log(f"  skip {rid} (summary not ready)")
            continue
        title, body = format_digest(m)
        obs_path = write_pending_obsidian(m["recording_id"], title, body, DIGEST_TARGET_CHANNEL)
        dm_ts = dm_anish(body, m["recording_id"], obs_path, DIGEST_TARGET_CHANNEL)
        state["pending"][rid] = {
            "title": title,
            "body": body,
            "obsidian_path": str(obs_path),
            "dm_ts": dm_ts,
            "target_channel": DIGEST_TARGET_CHANNEL,
            "created": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": (now + timedelta(hours=EXPIRES_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        _log(f"  drafted {rid} '{title[:60]}' -> obsidian {obs_path.name}" + (f", DM ts={dm_ts}" if dm_ts else ""))
        drafted += 1
    state["last_check"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return drafted


def approval_phase(state: dict) -> tuple[int, int, int]:
    """Check pending digests for approval signals. Return (approved, dismissed, expired) counts."""
    now = datetime.now(timezone.utc)
    approved_ids = []
    dismissed_ids = []
    expired_ids = []
    # Need DM channel_id for reaction checks
    dm_channel_id = None
    if SLACK_BOT_TOKEN and SLACK_ANISH_USER_ID:
        dm_channel_id = open_dm_channel(SLACK_ANISH_USER_ID)

    for rid, p in list(state["pending"].items()):
        obs_path = Path(p["obsidian_path"])
        # Check Obsidian frontmatter
        result = read_obsidian_approval(obs_path)
        # Check Slack reactions
        if not result and dm_channel_id and p.get("dm_ts"):
            result = check_slack_reactions(dm_channel_id, p["dm_ts"])
        # Check expiry
        if not result:
            try:
                exp = datetime.fromisoformat(p["expires_at"].replace("Z", "+00:00"))
                if now > exp:
                    result = "expired"
            except Exception:
                pass
        if result == "approve":
            # Post to target channel
            if p.get("target_channel"):
                ok, info = post_to_target_channel(p["target_channel"], p["body"])
                if ok:
                    _log(f"  APPROVED + posted {rid} -> {p['target_channel']} ts={info}")
                    approved_ids.append(rid)
                else:
                    _log(f"  [err] post failed for approved {rid}: {info}")
                    continue  # leave pending for retry
            else:
                _log(f"  approved but no target_channel set for {rid} — kept in Obsidian only")
                approved_ids.append(rid)
        elif result == "dismiss":
            _log(f"  DISMISSED {rid} '{p['title'][:60]}'")
            dismissed_ids.append(rid)
        elif result == "expired":
            _log(f"  EXPIRED {rid} '{p['title'][:60]}' (>48h no response)")
            expired_ids.append(rid)

    for rid in approved_ids:
        state["pending"].pop(rid, None)
        state["posted"].append(rid)
    for rid in dismissed_ids + expired_ids:
        state["pending"].pop(rid, None)
        state["dismissed"].append(rid)
    # Trim history
    state["posted"] = state["posted"][-500:]
    state["dismissed"] = state["dismissed"][-500:]
    return len(approved_ids), len(dismissed_ids), len(expired_ids)


def main():
    if not FATHOM_API_KEY:
        _log("[err] FATHOM_API_KEY not set")
        sys.exit(1)
    state = load_state()
    drafted = discovery_phase(state)
    approved, dismissed, expired = approval_phase(state)
    save_state(state)
    _log(f"summary: {drafted} new drafted, {approved} approved+posted, {dismissed} dismissed, {expired} expired, {len(state['pending'])} still pending")


if __name__ == "__main__":
    main()
