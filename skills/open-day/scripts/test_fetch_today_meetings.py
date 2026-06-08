"""Pure-function tests for fetch_today_meetings — runs in milliseconds, no IMAP.

Targets the bug classes verification has already caught in this script:
  - Google Calendar `_R<date>T<time>` UID dedup (series_id collapse)
  - cross-timezone collapse for override-replaces-master (UTC normalization)
  - cancelled-master propagation
  - all-day events emitting a non-null end_local

Run:  python -m pytest test_fetch_today_meetings.py -v
"""
from datetime import date, datetime, timezone

import pytest
from dateutil import tz
from icalendar import Calendar, Event

import fetch_today_meetings as ftm

LOCAL_TZ = tz.gettz("America/Denver")


@pytest.mark.parametrize(
    "uid,expected",
    [
        ("abc_R20260326T170000@google.com", "abc@google.com"),
        ("abc_R20260427T170000@google.com", "abc@google.com"),
        ("abc_R20260326@google.com", "abc@google.com"),
        ("abc_R1@google.com", "abc@google.com"),
        ("plain@google.com", "plain@google.com"),
        ("foo_RANDOM@google.com", "foo_RANDOM@google.com"),
        ("foo_R@google.com", "foo_R@google.com"),
    ],
)
def test_series_id(uid, expected):
    assert ftm._series_id(uid) == expected


def test_to_utc_iso_collapses_timezones():
    # 13:00 ET == 11:00 MT == 17:00 UTC
    assert ftm._to_utc_iso("2026-04-30T13:00:00-04:00") == ftm._to_utc_iso("2026-04-30T11:00:00-06:00")


def test_to_utc_iso_handles_none_and_garbage():
    assert ftm._to_utc_iso(None) is None
    assert ftm._to_utc_iso("") is None
    assert ftm._to_utc_iso("not-a-date") == "not-a-date"  # passthrough on parse failure


def _make_event(uid, start_local, *, sequence=0, dtstamp="2026-04-29T00:00:00+00:00",
                status="CONFIRMED", recurrence_id=None, summary="Meeting"):
    return {
        "uid": uid,
        "sequence": sequence,
        "dtstamp": dtstamp,
        "summary": summary,
        "status": status,
        "start_local": start_local,
        "end_local": start_local,
        "organizer": "",
        "attendees": [],
        "location": "",
        "recurrence_id": recurrence_id,
        "is_recurring_master": recurrence_id is None,
    }


def test_reconcile_collapses_R_variants_at_same_time():
    events = [
        _make_event("abc_R20260326T170000@google.com", "2026-04-30T11:00:00-06:00",
                    dtstamp="2026-03-26T17:35:00+00:00"),
        _make_event("abc_R20260427T170000@google.com", "2026-04-30T11:00:00-06:00",
                    dtstamp="2026-04-27T15:15:00+00:00"),
    ]
    out = ftm.reconcile(events)
    assert len(out) == 1
    # Latest dtstamp wins.
    assert out[0]["dtstamp"] == "2026-04-27T15:15:00+00:00"


def test_reconcile_override_replaces_master_across_timezones():
    # Master expansion at 11:00 MT == 17:00 UTC.
    # Override has RECURRENCE-ID at 13:00 ET == 17:00 UTC. Same moment, different strings.
    events = [
        _make_event("abc@google.com", "2026-04-30T11:00:00-06:00", summary="Master"),
        _make_event("abc@google.com", "2026-04-30T11:00:00-06:00", summary="Override",
                    recurrence_id="2026-04-30T13:00:00-04:00", sequence=1),
    ]
    out = ftm.reconcile(events)
    assert len(out) == 1
    assert out[0]["summary"] == "Override"


def test_reconcile_cancelled_series_drops_all_instances():
    events = [
        _make_event("abc@google.com", "2026-04-30T11:00:00-06:00", status="CANCELLED"),
        _make_event("abc@google.com", "2026-04-30T11:00:00-06:00", summary="Override",
                    recurrence_id="2026-04-30T11:00:00-06:00"),
        _make_event("xyz@google.com", "2026-04-30T14:00:00-06:00", summary="Other"),
    ]
    out = ftm.reconcile(events)
    assert [e["summary"] for e in out] == ["Other"]


def test_reconcile_freshness_higher_sequence_wins():
    events = [
        _make_event("abc@google.com", "2026-04-30T09:00:00-06:00", sequence=2, summary="Newer"),
        _make_event("abc@google.com", "2026-04-30T09:00:00-06:00", sequence=1, summary="Older"),
    ]
    out = ftm.reconcile(events)
    assert len(out) == 1
    assert out[0]["summary"] == "Newer"


def test_expand_event_all_day_emits_non_null_end_local():
    """All-day events have date (not datetime) DTSTART and often no DTEND.

    Regression guard for the bug where end_local came out as null for all-day events.
    """
    cal = Calendar()
    ev = Event()
    ev.add("UID", "allday@google.com")
    ev.add("SUMMARY", "Holiday")
    ev.add("DTSTART", date(2026, 4, 30))
    ev.add("DTSTAMP", datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc))
    cal.add_component(ev)

    occurrences = ftm.expand_event(ev, date(2026, 4, 30), LOCAL_TZ)
    assert len(occurrences) == 1
    assert occurrences[0]["start_local"] is not None
    assert occurrences[0]["end_local"] is not None, "all-day end_local must not be null"
    # Span should be ~24h.
    start = datetime.fromisoformat(occurrences[0]["start_local"])
    end = datetime.fromisoformat(occurrences[0]["end_local"])
    assert (end - start).total_seconds() == 24 * 3600


def test_load_env_file_overrides_stale_env_vars(tmp_path, monkeypatch):
    """The .env file should win over a stale env var (regression for setdefault bug)."""
    env_file = tmp_path / "open-day.env"
    env_file.write_text("GMAIL_USER=fresh@example.com\nGMAIL_APP_PASSWORD=newpass\n")

    monkeypatch.setenv("GMAIL_USER", "stale@example.com")
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)

    ftm.load_env_file(env_file)

    import os
    assert os.environ["GMAIL_USER"] == "fresh@example.com"
    assert os.environ["GMAIL_APP_PASSWORD"] == "newpass"
