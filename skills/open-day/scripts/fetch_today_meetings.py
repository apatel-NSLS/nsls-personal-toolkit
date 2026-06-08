"""Pull today's calendar invites from Gmail via IMAP and emit them as JSON.

Used as a fallback when the Google Workspace MCP isn't available (e.g. the 7 a.m.
scheduled `/open-day` runs in a headless Claude session that can't reach the
first-party `claude.ai Gmail` connector).

Auth: GMAIL_USER + GMAIL_APP_PASSWORD env vars, or `~/.claude/credentials/open-day.env`
(auto-loaded if either env var is missing — values from the file always win when
loaded, so a stale Windows User-level env var can't shadow the canonical .env).
Generate the app password at https://myaccount.google.com/apppasswords.

Usage:
  python fetch_today_meetings.py [--date YYYY-MM-DD] [--lookback-days 90]

Env:
  GMAIL_USER, GMAIL_APP_PASSWORD — IMAP credentials.
  BUILDER_TIMEZONE — IANA tz name (default: America/Denver).

Output (JSON to stdout):
  {
    "events":   [<event dict>, ...]   # sorted by start_local, deduped, cancelled stripped
    "warnings": ["..."]                # user-visible failures (auth, fetch, fallback)
  }

The process exits 0 even on Gmail/parse failures — failures surface via the
`warnings` array so the caller can prepend them to the daily note instead of
silently rendering an empty calendar.
"""
import argparse
import email
import imaplib
import io
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from dateutil import tz
from dateutil.rrule import rrulestr
from icalendar import Calendar

def _force_utf8_stdout() -> None:
    """Ensure stdout emits UTF-8 (Windows defaults to cp1252 without this)."""
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
DEFAULT_TZ = "America/Denver"
CREDENTIALS_FILE = Path.home() / ".claude" / "credentials" / "open-day.env"
FETCH_CHUNK = 200  # IMAP servers cap how many ids one FETCH can handle


_warnings: list[str] = []


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def warn(msg: str) -> None:
    """Record a user-visible warning AND log it to stderr."""
    _warnings.append(msg)
    log(f"[warn] {msg}")


def load_env_file(path: Path) -> None:
    """Populate os.environ from a KEY=VALUE file. Missing file is a silent no-op.

    Values from the file always win — using `setdefault` would let a stale
    Windows User-level env var shadow the canonical credential.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def to_local(dt, local_tz):
    """Coerce a date/datetime from icalendar into a timezone-aware local datetime."""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(local_tz)
    if isinstance(dt, date):
        return datetime.combine(dt, time(0, 0), tzinfo=local_tz)
    return None


def stream_invite_payloads(user: str, password: str, lookback_days: int) -> Iterator[bytes]:
    """Yield raw .ics payload bytes from Gmail invites in the lookback window.

    Streams to keep peak memory bounded — N×RFC822 messages are never all in scope
    at the same time. Bulk-fetches in chunks to avoid the per-id round-trip cost.
    """
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        mail.login(user, password)
        if mail.select('"[Gmail]/All Mail"', readonly=True)[0] != "OK":
            warn("could not select [Gmail]/All Mail; falling back to INBOX (may miss invites)")
            mail.select("INBOX", readonly=True)

        # X-GM-RAW takes Gmail search-bar syntax. filename:ics catches cancellations
        # and updates that has:invite (Google's curated filter) sometimes drops.
        status, data = mail.search(None, "X-GM-RAW", f'"filename:ics newer_than:{lookback_days}d"')
        if status != "OK" or not data or not data[0]:
            log(f"no invite messages found in last {lookback_days}d")
            return

        ids = data[0].split()
        log(f"found {len(ids)} candidate messages with .ics attachments")

        for chunk_start in range(0, len(ids), FETCH_CHUNK):
            chunk = ids[chunk_start:chunk_start + FETCH_CHUNK]
            try:
                status, parts = mail.fetch(b",".join(chunk), "(RFC822)")
            except Exception as e:
                log(f"  [warn] bulk fetch failed for chunk starting at {chunk_start}: {e}")
                continue
            if status != "OK" or not parts:
                continue
            for part in parts:
                if not (isinstance(part, tuple) and len(part) == 2):
                    continue
                try:
                    msg = email.message_from_bytes(part[1])
                except (email.errors.MessageError, ValueError) as e:
                    log(f"  [warn] message parse failed: {e}")
                    continue
                for sub in msg.walk():
                    ctype = (sub.get_content_type() or "").lower()
                    fname = (sub.get_filename() or "").lower()
                    if ctype == "text/calendar" or fname.endswith(".ics"):
                        body = sub.get_payload(decode=True)
                        if body:
                            yield body
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def expand_event(vevent, target_date, local_tz) -> list[dict]:
    """Return zero or more occurrence dicts for events that fall on target_date."""
    summary = str(vevent.get("SUMMARY") or "").strip()
    location = str(vevent.get("LOCATION") or "").strip()
    organizer = str(vevent.get("ORGANIZER") or "").replace("mailto:", "").strip()
    status = str(vevent.get("STATUS") or "").upper()
    uid = str(vevent.get("UID") or "")
    sequence = int(vevent.get("SEQUENCE", 0) or 0)
    dtstamp = vevent.get("DTSTAMP")

    attendees_raw = vevent.get("ATTENDEE", [])
    if not isinstance(attendees_raw, list):
        attendees_raw = [attendees_raw]
    attendees = [s for s in (str(a).replace("mailto:", "").strip() for a in attendees_raw) if s]

    dtstart_field = vevent.get("DTSTART")
    if not dtstart_field:
        return []
    dtstart = dtstart_field.dt
    dtend_field = vevent.get("DTEND")
    dtend = dtend_field.dt if dtend_field else None

    rrule = vevent.get("RRULE")
    recurrence_id = vevent.get("RECURRENCE-ID")

    # All-day events have date (not datetime) types; preserve their natural span.
    if isinstance(dtstart, datetime):
        default_duration = timedelta(hours=1)
    else:
        default_duration = timedelta(days=1)
    span = (dtend - dtstart) if dtend else default_duration
    if dtend is None:
        dtend = dtstart + span  # ensures emit() always gets a non-None end

    target_start = datetime.combine(target_date, time(0, 0), tzinfo=local_tz)
    target_end = target_start + timedelta(days=1)
    occurrences = []

    def emit(start_dt, end_dt):
        local_start = to_local(start_dt, local_tz)
        if local_start is None or not (target_start <= local_start < target_end):
            return
        local_end = to_local(end_dt, local_tz)
        rid = None
        if recurrence_id:
            rid_val = recurrence_id.dt
            rid = rid_val.isoformat() if isinstance(rid_val, datetime) else str(rid_val)
        occurrences.append({
            "uid": uid,
            "sequence": sequence,
            "dtstamp": dtstamp.dt.isoformat() if dtstamp and isinstance(dtstamp.dt, datetime) else None,
            "summary": summary,
            "status": status,
            "start_local": local_start.isoformat(),
            "end_local": local_end.isoformat() if local_end else None,
            "organizer": organizer,
            "attendees": attendees,
            "location": location,
            "recurrence_id": rid,
            "is_recurring_master": bool(rrule and not recurrence_id),
        })

    if rrule:
        rule_text = rrule.to_ical().decode() if hasattr(rrule, "to_ical") else str(rrule)
        try:
            base = dtstart if isinstance(dtstart, datetime) else datetime.combine(dtstart, time(0, 0))
            if isinstance(base, datetime) and base.tzinfo is None:
                base = base.replace(tzinfo=local_tz)
            for occ in rrulestr(rule_text, dtstart=base).between(
                target_start - timedelta(days=1), target_end + timedelta(days=1), inc=True
            ):
                emit(occ, occ + span)
        except Exception as e:
            log(f"  [warn] rrule expansion failed for {uid!r}: {e}")
    else:
        emit(dtstart, dtend)

    return occurrences


_R_UID_SUFFIX = re.compile(r"_R\d+T?\d*(?=@|$)")


def _series_id(uid: str) -> str:
    """Strip Google Calendar's `_R<date>T<time>` versioning suffix.

    Google generates a new UID variant each time a recurring series is modified
    "this and following" — `abc_R20260326T170000@google.com` and
    `abc_R20260427T170000@google.com` are the same series, just versioned.
    Strict UID-based dedup (RFC 5545) treats them as different events; collapsing
    by series_id matches what a human reader expects.
    """
    return _R_UID_SUFFIX.sub("", uid)


def _to_utc_iso(iso_str: str | None) -> str | None:
    """Normalize an ISO-8601 timestamp to UTC for cross-timezone comparison."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str).astimezone(timezone.utc).isoformat()
    except ValueError:
        return iso_str


def reconcile(events: Iterable[dict]) -> list[dict]:
    """Resolve duplicate invites, cancellations, and overrides into a clean list.

    DTSTAMP per RFC 5545 is always UTC, so lex compare on the ISO-8601 string
    matches chronological order — safe to use as the freshness tiebreaker. Keys
    on (series_id, recurrence_id, start_local) so two Google `_R` UID variants
    that expand to the same time collapse into one. After per-key dedup, master
    expansions whose start time matches an override's RECURRENCE-ID are dropped
    (the override replaces the original instance per RFC 5545).
    """
    by_key: dict[tuple, dict] = {}
    for ev in events:
        key = (_series_id(ev["uid"]), ev.get("recurrence_id"), ev.get("start_local"))
        prev = by_key.get(key)
        freshness = (ev.get("sequence") or 0, ev.get("dtstamp") or "")
        prev_freshness = (prev.get("sequence") or 0, prev.get("dtstamp") or "") if prev else None
        if prev_freshness is None or freshness >= prev_freshness:
            by_key[key] = ev

    cancelled_series = {
        sid for (sid, rid, _), ev in by_key.items()
        if rid is None and ev.get("status") == "CANCELLED"
    }

    override_targets = {
        (sid, _to_utc_iso(rid))
        for (sid, rid, _), _ev in by_key.items()
        if rid is not None
    }

    out = []
    for (sid, rid, start_local), ev in by_key.items():
        if ev.get("status") == "CANCELLED" or sid in cancelled_series:
            continue
        if rid is None and (sid, _to_utc_iso(start_local)) in override_targets:
            continue
        out.append(ev)
    out.sort(key=lambda e: e.get("start_local") or "")
    return out


def emit_envelope(events: list[dict]) -> None:
    print(json.dumps({"events": events, "warnings": list(_warnings)}, indent=2, default=str))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="target date YYYY-MM-DD (default: today in builder timezone)")
    ap.add_argument("--lookback-days", type=int, default=90, help="how far back to look for invites")
    args = ap.parse_args()

    if not os.environ.get("GMAIL_APP_PASSWORD") or not os.environ.get("GMAIL_USER"):
        load_env_file(CREDENTIALS_FILE)

    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not pw:
        warn(f"GMAIL_USER and GMAIL_APP_PASSWORD must be set (env vars or {CREDENTIALS_FILE})")
        emit_envelope([])
        return 0

    tz_name = os.environ.get("BUILDER_TIMEZONE", DEFAULT_TZ)
    local_tz = tz.gettz(tz_name)
    if local_tz is None:
        warn(f"unknown timezone {tz_name!r}; falling back to {DEFAULT_TZ}")
        local_tz = tz.gettz(DEFAULT_TZ)

    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now(local_tz).date()
    )
    log(f"target date: {target_date} ({tz_name})")

    try:
        payloads = list(stream_invite_payloads(user, pw, args.lookback_days))
    except imaplib.IMAP4.error as e:
        warn(f"Gmail IMAP login/select failed: {e}")
        emit_envelope([])
        return 0
    except Exception as e:
        warn(f"Gmail fetch failed: {e}")
        emit_envelope([])
        return 0

    log(f"extracted {len(payloads)} ICS payloads")
    all_events = []
    for body in payloads:
        try:
            cal = Calendar.from_ical(body)
        except Exception as e:
            log(f"  [debug] ICS parse failed: {e} (first 120 chars: {body[:120]!r})")
            continue
        for component in cal.walk("VEVENT"):
            try:
                all_events.extend(expand_event(component, target_date, local_tz))
            except Exception as e:
                log(f"  [debug] event expansion failed: {e}")

    final = reconcile(all_events)
    log(f"emitting {len(final)} event(s) for {target_date}")
    emit_envelope(final)
    return 0


if __name__ == "__main__":
    _force_utf8_stdout()
    sys.exit(main())
