"""Fetch recent Gmail threads with a given email address via IMAP.

Auth: reads GMAIL_USER + GMAIL_APP_PASSWORD env vars.
Generate app password at https://myaccount.google.com/apppasswords (16-char string).

Usage:
  python fetch_gmail.py --email kprentiss@nsls.org --days 14

Output: markdown summary of threads with that person.
"""
import argparse
import email
import email.utils
import imaplib
import io
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Force UTF-8 stdout on Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def decode_mime(raw: str | bytes | None) -> str:
    if not raw:
        return ""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="replace")
        except Exception:
            raw = raw.decode("latin-1", errors="replace")
    parts = decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out).strip()


def body_snippet(msg, max_chars: int = 400) -> str:
    """Extract a short plain-text snippet from the message."""
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text = payload.decode(charset, errors="replace")
                    except LookupError:
                        text = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
    # Strip quoted reply blocks heuristically
    text = re.split(r"^\s*On\s.+wrote:\s*$", text, maxsplit=1, flags=re.MULTILINE)[0]
    text = re.sub(r"\n>.*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def fetch_threads_with(person_email: str, user: str, app_password: str, days: int = 14, limit: int = 20):
    if not EMAIL_RE.match(person_email):
        raise ValueError(f"refusing unsafe email for IMAP query: {person_email!r}")
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since_dt.strftime("%d-%b-%Y")  # IMAP date format

    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(user, app_password)
    # Gmail's "All Mail" folder requires quoted form; fall back to INBOX if rejected
    all_mail_box = '"[Gmail]/All Mail"'
    status, _ = mail.select(all_mail_box, readonly=True)
    if status != "OK":
        mail.select("INBOX", readonly=True)

    # Gmail's X-GM-RAW search; EMAIL_RE above already constrains person_email to safe chars
    raw_query = f'(from:{person_email} OR to:{person_email} OR cc:{person_email}) newer_than:{days}d'
    status, data = mail.search(None, "X-GM-RAW", f'"{raw_query}"')
    if status != "OK" or not data or not data[0]:
        # IMAP-native fallback — parenthesize the OR so it binds before SINCE
        crit = f'(OR FROM "{person_email}" TO "{person_email}") SINCE "{since_str}"'
        status, data = mail.search(None, crit)
    ids = (data[0].split() if data and data[0] else [])[-limit:]  # most recent N

    messages = []
    for msg_id in reversed(ids):  # newest first
        try:
            # One round-trip for both RFC822 body and Gmail thread id
            status, data = mail.fetch(msg_id, "(RFC822 X-GM-THRID)")
            if status != "OK" or not data:
                continue
            raw_msg = None
            thrid = None
            for part in data:
                if isinstance(part, tuple) and len(part) == 2 and raw_msg is None:
                    raw_msg = part[1]
                if isinstance(part, bytes):
                    m = re.search(rb"X-GM-THRID (\d+)", part)
                    if m:
                        thrid = m.group(1).decode()
                elif isinstance(part, tuple):
                    m = re.search(rb"X-GM-THRID (\d+)", part[0] or b"")
                    if m and not thrid:
                        thrid = m.group(1).decode()
            if not raw_msg:
                continue
            msg = email.message_from_bytes(raw_msg)
            subject = decode_mime(msg.get("Subject"))
            from_ = decode_mime(msg.get("From"))
            to_ = decode_mime(msg.get("To"))
            date = msg.get("Date")
            try:
                date_dt = email.utils.parsedate_to_datetime(date)
                date_str = date_dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = date or ""
            messages.append({
                "thrid": thrid,
                "subject": subject,
                "from": from_,
                "to": to_,
                "date": date_str,
                "snippet": body_snippet(msg),
            })
        except Exception as e:
            print(f"  [warn] failed to fetch {msg_id!r}: {e}", file=sys.stderr)

    mail.logout()
    return messages


def dedupe_threads(messages):
    """Keep only the newest message per thread for brevity."""
    seen = set()
    out = []
    for m in messages:
        key = m.get("thrid") or m["subject"]
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def format_markdown(person_email: str, days: int, messages) -> str:
    if not messages:
        return f"**Gmail (last {days}d with {person_email}):** no recent threads.\n"
    lines = [f"**Gmail threads with {person_email} (last {days}d, newest first):**", ""]
    threads = dedupe_threads(messages)[:8]
    for m in threads:
        direction = "->" if person_email.lower() in m.get("to", "").lower() else "<-"
        lines.append(f"- `{m['date']}` {direction} **{m['subject'][:80]}**")
        if m["snippet"]:
            lines.append(f"  > {m['snippet'][:240]}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True, help="the other party's email")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    user = os.environ.get("GMAIL_USER", "apatel@nsls.org")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not pw:
        print("GMAIL_APP_PASSWORD env var not set — skipping Gmail.", file=sys.stderr)
        print("")  # stdout empty so orchestrator can inline nothing
        return

    try:
        messages = fetch_threads_with(args.email, user, pw, days=args.days, limit=args.limit)
    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}", file=sys.stderr)
        return
    except Exception as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return

    print(format_markdown(args.email, args.days, messages))


if __name__ == "__main__":
    main()
